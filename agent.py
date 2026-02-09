#!/usr/bin/env python3
"""
Hospital Voice Bot - LiveKit Agent

Simulates patients calling hospital phone systems for QA testing.
Uses LiveKit Agents with Deepgram STT/TTS and Claude LLM.
Includes audio recording via LiveKit Egress.
"""

# SSL fix for macOS (must be before other imports)
import os
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

# Standard library
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterable

# Third-party
from dotenv import load_dotenv
from livekit import api
from livekit.agents import (
    Agent,
    AgentSession,
    ModelSettings,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
)
from livekit.plugins import deepgram, silero
from livekit.plugins.anthropic import llm as anthropic_llm

# Local
from scenarios import PatientScenario, SCENARIOS

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

AGENT_NAME = "hospital-patient-bot"

# Output directories
RECORDINGS_DIR = Path(__file__).parent / "recordings"
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"
RECORDINGS_DIR.mkdir(exist_ok=True)
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

# Model configuration
STT_MODEL = "nova-2"
LLM_MODEL = "claude-sonnet-4-20250514"
TTS_MODEL = "aura-asteria-en"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("patient-bot")

# =============================================================================
# Prompt Template
# =============================================================================

PATIENT_PROMPT = """You are {name}, a patient calling a hospital phone system.

Date of birth: {dob}
Goal: {goal}
{details}

Guidelines:
- Keep responses to 1-2 sentences
- Speak naturally, like a real phone call
- Provide your name and DOB when asked
- Stay focused on your goal
- If unsure about something, say so

Begin by stating why you're calling."""

# =============================================================================
# Call Recorder (LiveKit Egress)
# =============================================================================


class CallRecorder:
    """Records call audio and transcripts using LiveKit Egress."""

    def __init__(self, scenario_name: str, room_name: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = scenario_name.replace(" ", "_").lower()
        self.base_name = f"{timestamp}_{safe_name}"
        self.room_name = room_name
        self.scenario_name = scenario_name

        # File paths
        self.audio_path = RECORDINGS_DIR / f"{self.base_name}.ogg"
        self.transcript_path = TRANSCRIPTS_DIR / f"{self.base_name}.txt"

        # State
        self.egress_id: str | None = None
        self.transcript_entries: list[str] = []

        # Write transcript header
        self._init_transcript()

    def _init_transcript(self):
        """Initialize transcript file with header."""
        with open(self.transcript_path, "w") as f:
            f.write(f"Call Transcript: {self.scenario_name}\n")
            f.write(f"Room: {self.room_name}\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write(f"Audio: {self.audio_path.name}\n")
            f.write("-" * 50 + "\n")

    def _append_transcript(self, speaker: str, text: str):
        """Append a line to the transcript."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {speaker}: {text}"
        self.transcript_entries.append(line)
        with open(self.transcript_path, "a") as f:
            f.write(line + "\n")
        logger.info(f"{speaker}: {text}")

    def log_hospital(self, text: str):
        """Log hospital system speech."""
        self._append_transcript("HOSPITAL", text)

    def log_patient(self, text: str):
        """Log patient bot speech."""
        self._append_transcript("PATIENT ", text)

    async def start_recording(self, lk_api: api.LiveKitAPI):
        """Start LiveKit Egress audio recording."""
        try:
            # Request room composite egress (audio only)
            egress_request = api.RoomCompositeEgressRequest(
                room_name=self.room_name,
                audio_only=True,
                file_outputs=[
                    api.EncodedFileOutput(
                        file_type=api.EncodedFileType.OGG,
                        filepath=str(self.audio_path),
                    )
                ],
            )

            response = await lk_api.egress.start_room_composite_egress(egress_request)
            self.egress_id = response.egress_id
            logger.info(f"Recording started: {self.audio_path.name} (egress: {self.egress_id})")

        except Exception as e:
            logger.warning(f"Could not start recording: {e}")
            logger.info("Continuing without audio recording")

    async def stop_recording(self, lk_api: api.LiveKitAPI):
        """Stop the egress recording."""
        if self.egress_id:
            try:
                await lk_api.egress.stop_egress(api.StopEgressRequest(egress_id=self.egress_id))
                logger.info(f"Recording stopped: {self.audio_path.name}")
            except Exception as e:
                logger.warning(f"Could not stop recording: {e}")

    def finalize(self):
        """Finalize transcript with footer."""
        with open(self.transcript_path, "a") as f:
            f.write("-" * 50 + "\n")
            f.write(f"Ended: {datetime.now().isoformat()}\n")
            f.write(f"Entries: {len(self.transcript_entries)}\n")
        logger.info(f"Transcript saved: {self.transcript_path}")
        if self.audio_path.exists():
            logger.info(f"Audio saved: {self.audio_path}")


# =============================================================================
# Patient Agent
# =============================================================================


class PatientAgent(Agent):
    """Voice agent simulating a patient calling a hospital."""

    def __init__(self, scenario: PatientScenario, recorder: CallRecorder):
        instructions = self._build_instructions(scenario)
        super().__init__(instructions=instructions)
        self.scenario = scenario
        self.recorder = recorder

    def _build_instructions(self, scenario: PatientScenario) -> str:
        """Build the agent instructions from scenario."""
        details = ""
        if scenario.details:
            details = "Details:\n" + "\n".join(
                f"- {k}: {v}" for k, v in scenario.details.items()
            )

        return PATIENT_PROMPT.format(
            name=scenario.name,
            dob=scenario.date_of_birth,
            goal=scenario.goal,
            details=details,
        )

    async def _capture_text_stream(
        self, text_stream: AsyncIterable[str]
    ) -> AsyncIterable[str]:
        """Wrap text stream to capture output for transcript."""
        buffer: list[str] = []
        async for chunk in text_stream:
            buffer.append(chunk)
            yield chunk

        if buffer:
            full_text = "".join(buffer).strip()
            if full_text:
                self.recorder.log_patient(full_text)

    def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable:
        """Hook into TTS pipeline to capture agent speech."""
        captured_text = self._capture_text_stream(text)
        return Agent.default.tts_node(self, captured_text, model_settings)

    @function_tool
    async def hang_up(self) -> str:
        """End the call when the conversation is complete."""
        logger.info("Ending call")
        ctx = get_job_context()
        if ctx:
            await asyncio.sleep(1.0)
            await ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=ctx.room.name)
            )
        return "Call ended."


# =============================================================================
# Entrypoint
# =============================================================================


async def entrypoint(ctx: RunContext):
    """Agent entrypoint - handles outbound calls to hospital phone systems."""

    # Parse job metadata
    metadata = json.loads(ctx.job.metadata) if ctx.job.metadata else {}
    scenario_index = metadata.get("scenario_index", 0)
    phone_number = metadata.get("phone_number")
    sip_trunk_id = metadata.get("sip_trunk_id")

    # Validate scenario
    if scenario_index >= len(SCENARIOS):
        logger.error(f"Invalid scenario index: {scenario_index}")
        return

    scenario = SCENARIOS[scenario_index]
    logger.info(f"Scenario: {scenario.name} | Goal: {scenario.goal}")

    # Initialize recorder (handles both audio and transcripts)
    recorder = CallRecorder(scenario.name, ctx.room.name)

    # Create agent and session
    agent = PatientAgent(scenario, recorder)
    session = AgentSession(
        stt=deepgram.STT(model=STT_MODEL),
        llm=anthropic_llm.LLM(model=LLM_MODEL),
        tts=deepgram.TTS(model=TTS_MODEL),
        vad=silero.VAD.load(),
    )

    # Capture hospital speech
    @session.on("user_input_transcribed")
    def on_hospital_speech(event):
        if event.is_final:
            recorder.log_hospital(event.transcript)

    # Start session
    await session.start(room=ctx.room, agent=agent)

    # Place outbound call
    if phone_number and sip_trunk_id:
        logger.info(f"Calling {phone_number}")
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=sip_trunk_id,
                    sip_call_to=phone_number,
                    participant_identity=f"hospital-{phone_number}",
                    wait_until_answered=True,
                )
            )
            logger.info("Connected")

            # Start audio recording after call connects
            await recorder.start_recording(ctx.api)

        except api.TwirpError as e:
            logger.error(f"Call failed: {e.message}")
            recorder.finalize()
            await ctx.shutdown()
            return

    # Begin conversation
    await session.generate_reply(instructions="State why you're calling.")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=AGENT_NAME,
        )
    )
