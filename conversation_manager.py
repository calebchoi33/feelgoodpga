"""
Manages the conversation flow between the patient bot and hospital agent.
"""

import json
import asyncio
import audioop
import logging
import time
from typing import Callable, Awaitable

from scenarios import PatientScenario
from stt_service import STTService
from llm_service import LLMService
from tts_service import TTSService
from recorder import CallRecording
from analyzer import ConversationAnalyzer, generate_bug_report

logger = logging.getLogger(__name__)

AudioSender = Callable[[bytes], Awaitable[None]]

# Twilio expects ~20ms chunks at 8kHz mulaw = 160 bytes
CHUNK_SIZE = 160
CHUNK_DURATION = 0.02  # 20ms

# Wait for agent to finish speaking before responding
RESPONSE_DELAY = 1.2  # seconds to wait after last transcript before responding
SILENCE_THRESHOLD = 400  # Audio energy threshold for voice activity detection
VOICE_ACTIVITY_TIMEOUT = 0.8  # seconds of silence required before responding

# Sentence-ending punctuation that suggests agent has finished a thought
SENTENCE_ENDINGS = ('.', '?', '!')


class ConversationManager:
    """Orchestrates the conversation between patient bot and hospital agent."""

    def __init__(
        self,
        scenario: PatientScenario,
        stt: STTService,
        llm: LLMService,
        tts: TTSService,
        audio_sender: AudioSender,
        call_id: str,
    ):
        self.scenario = scenario
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.audio_sender = audio_sender

        self.is_bot_speaking = False
        self.pending_agent_text: list[str] = []  # Buffer for agent speech
        self.response_task: asyncio.Task | None = None  # Delayed response task
        self.last_voice_activity: float = 0  # Timestamp of last detected voice
        self.call_started_at = time.time()

        self.recording = CallRecording(
            call_id=call_id,
            scenario_name=scenario.name,
            scenario_goal=scenario.goal,
        )

    async def start(self):
        """Start the conversation - generate initial greeting."""
        logger.info(f"Starting conversation as {self.scenario.name}")
        await self.stt.start_stream(self.on_transcript)

        # Generate and speak initial greeting
        await self._generate_and_speak(None)

    async def on_transcript(self, text: str, is_final: bool):
        """Handle incoming transcript from STT."""
        if not is_final:
            return

        logger.info(f"Agent: {text}")
        self.recording.add_utterance("agent", text)

        # Don't respond while bot is speaking
        if self.is_bot_speaking:
            logger.info(f"Buffering agent speech (bot is speaking)")
            self.pending_agent_text.append(text)
            return

        # Cancel any pending response - agent is still talking
        if self.response_task and not self.response_task.done():
            self.response_task.cancel()

        # Buffer this speech
        self.pending_agent_text.append(text)

        # Schedule response after delay (gives agent time to finish)
        self.response_task = asyncio.create_task(self._delayed_response())

    async def _delayed_response(self):
        """Wait for agent to finish speaking, then respond."""
        try:
            await asyncio.sleep(RESPONSE_DELAY)

            # Check if there's still voice activity - wait for silence
            while time.time() - self.last_voice_activity < VOICE_ACTIVITY_TIMEOUT:
                logger.debug("Voice activity detected, waiting for silence...")
                await asyncio.sleep(0.1)

            # Combine all buffered speech
            if self.pending_agent_text:
                original_count = len(self.pending_agent_text)
                combined_text = " ".join(self.pending_agent_text)

                # If the text doesn't end with sentence-ending punctuation,
                # wait a bit longer in case agent is mid-sentence
                if not combined_text.rstrip().endswith(SENTENCE_ENDINGS):
                    logger.debug(f"No sentence ending detected, waiting longer...")
                    await asyncio.sleep(0.5)

                    # Check again if more text came in during the wait
                    if len(self.pending_agent_text) > original_count:
                        # More text arrived, recombine and check voice activity again
                        combined_text = " ".join(self.pending_agent_text)
                        while time.time() - self.last_voice_activity < VOICE_ACTIVITY_TIMEOUT:
                            await asyncio.sleep(0.1)

                self.pending_agent_text = []
                logger.info(f"Agent finished, responding to: {combined_text}")
                await self._generate_and_speak(combined_text)

        except asyncio.CancelledError:
            # Agent is still talking, response will be rescheduled
            pass

    def add_inbound_audio(self, mulaw_bytes: bytes):
        """Record inbound audio (from agent/hospital). Converts mulaw to PCM."""
        pcm_bytes = audioop.ulaw2lin(mulaw_bytes, 2)
        self.recording.add_inbound_audio(pcm_bytes)

        # Voice activity detection - check if agent is still speaking
        try:
            rms = audioop.rms(pcm_bytes, 2)
            if rms > SILENCE_THRESHOLD:
                self.last_voice_activity = time.time()
        except Exception:
            pass

    async def _generate_and_speak(self, agent_text: str | None):
        """Generate patient response and speak it."""
        self.is_bot_speaking = True

        try:
            # Generate response
            response = await self.llm.generate_response(agent_text)
            logger.info(f"Patient: {response}")
            self.recording.add_utterance("patient", response)

            # Synthesize to audio
            pcm_audio = await self.tts.synthesize(response)

            # Capture position RIGHT BEFORE sending - this is when audio starts playing
            start_position = len(self.recording.inbound_audio)

            # Send audio in chunks (this takes time as audio plays)
            await self._send_audio_chunks(pcm_audio)

            # Record outbound audio with the position where it STARTED playing
            self.recording.add_outbound_audio(pcm_audio, start_position)

        except Exception as e:
            logger.error(f"Error in generate_and_speak: {e}")
        finally:
            self.is_bot_speaking = False

            # If agent spoke while we were talking, schedule a response
            if self.pending_agent_text:
                logger.info(f"Agent spoke while bot was talking, scheduling response")
                self.response_task = asyncio.create_task(self._delayed_response())

    async def _send_audio_chunks(self, pcm_audio: bytes):
        """Send audio to Twilio in chunks with timing."""
        # Calculate total duration for logging
        duration = len(pcm_audio) / (8000 * 2)  # 8kHz, 16-bit
        logger.info(f"Speaking for {duration:.1f}s")

        # Send in chunks
        for i in range(0, len(pcm_audio), CHUNK_SIZE):
            chunk = pcm_audio[i:i + CHUNK_SIZE]
            if chunk:
                await self.audio_sender(chunk)
                await asyncio.sleep(CHUNK_DURATION)

    async def stop(self):
        """Stop the conversation and cleanup."""
        # Cancel any pending response
        if self.response_task and not self.response_task.done():
            self.response_task.cancel()

        await self.stt.stop_stream()
        await self.tts.close()

        # Save recording and transcripts
        save_path = self.recording.save()
        logger.info(f"Saved recording to {save_path}")

        # Analyze conversation for quality issues
        try:
            transcript_path = save_path / "transcript.json"
            if transcript_path.exists():
                with open(transcript_path) as f:
                    transcript_data = json.load(f)

                analyzer = ConversationAnalyzer()
                issues = analyzer.analyze(transcript_data)
                analyzer.save_issues(save_path, issues)

                # Update aggregate bug report
                generate_bug_report()
        except Exception as e:
            logger.error(f"Analysis failed: {e}")

        logger.info(f"Conversation ended after {time.time() - self.call_started_at:.1f}s")
