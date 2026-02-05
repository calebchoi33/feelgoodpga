"""
Call recorder - saves audio and transcripts.
"""

import json
import wave
import audioop
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"


@dataclass
class Utterance:
    speaker: str  # "agent" or "patient"
    text: str
    timestamp: float


@dataclass
class OutboundSegment:
    """A segment of outbound audio with its byte position in the inbound stream."""
    byte_position: int  # byte offset in inbound audio stream
    audio: bytes


@dataclass
class CallRecording:
    call_id: str
    scenario_name: str
    scenario_goal: str
    start_time: float = field(default_factory=time.time)
    utterances: list[Utterance] = field(default_factory=list)
    inbound_audio: bytearray = field(default_factory=bytearray)
    outbound_segments: list[OutboundSegment] = field(default_factory=list)

    def add_utterance(self, speaker: str, text: str):
        """Add an utterance to the transcript."""
        self.utterances.append(Utterance(
            speaker=speaker,
            text=text,
            timestamp=time.time() - self.start_time,
        ))

    def add_inbound_audio(self, audio_bytes: bytes):
        """Add inbound audio data (from agent)."""
        self.inbound_audio.extend(audio_bytes)

    def add_outbound_audio(self, audio_bytes: bytes, start_position: int):
        """Add outbound audio at the specified inbound byte position (where playback started)."""
        logger.debug(f"Adding outbound segment at position {start_position}, audio_len={len(audio_bytes)}")
        self.outbound_segments.append(OutboundSegment(
            byte_position=start_position,
            audio=audio_bytes,
        ))

    def _build_aligned_outbound(self, total_length: int) -> bytes:
        """Build outbound audio with silence padding to align with inbound."""
        # Ensure total_length is even (aligned to 16-bit samples)
        total_length = total_length & ~1
        result = bytearray(total_length)  # Start with silence

        for segment in self.outbound_segments:
            # Align to 2-byte boundary (16-bit samples)
            start_pos = segment.byte_position & ~1

            # Ensure segment audio length is even
            audio = segment.audio
            if len(audio) % 2 == 1:
                audio = audio[:-1]

            # Skip invalid segments
            if start_pos >= total_length or start_pos < 0:
                logger.warning(f"Skipping segment with invalid position: {start_pos}")
                continue

            # Copy the audio data
            end_pos = min(start_pos + len(audio), total_length)
            result[start_pos:end_pos] = audio[:end_pos - start_pos]

        return bytes(result)

    def save(self) -> Path:
        """Save recording and transcripts. Returns the directory path."""
        # Create directory
        call_dir = TRANSCRIPTS_DIR / self.call_id
        call_dir.mkdir(parents=True, exist_ok=True)

        duration = time.time() - self.start_time

        # Save JSON transcript
        transcript_data = {
            "call_id": self.call_id,
            "scenario": {
                "name": self.scenario_name,
                "goal": self.scenario_goal,
            },
            "duration_seconds": round(duration, 1),
            "utterances": [asdict(u) for u in self.utterances],
        }
        json_path = call_dir / "transcript.json"
        with open(json_path, "w") as f:
            json.dump(transcript_data, f, indent=2)

        # Save readable text transcript
        text_path = call_dir / "transcript.txt"
        with open(text_path, "w") as f:
            f.write(f"Call ID: {self.call_id}\n")
            f.write(f"Scenario: {self.scenario_name}\n")
            f.write(f"Goal: {self.scenario_goal}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write("-" * 50 + "\n\n")
            for u in self.utterances:
                speaker = "AGENT" if u.speaker == "agent" else "PATIENT"
                f.write(f"[{u.timestamp:.1f}s] {speaker}: {u.text}\n\n")

        # Save audio files (8kHz, 16-bit PCM WAV)
        if self.inbound_audio:
            self._save_wav(call_dir / "inbound.wav", bytes(self.inbound_audio))

        if self.outbound_segments:
            # Build aligned outbound audio (with silence padding)
            aligned_outbound = self._build_aligned_outbound(len(self.inbound_audio))
            self._save_wav(call_dir / "outbound.wav", aligned_outbound)

            # Save raw outbound (just the speech, no silence) for reference
            raw_outbound = b''.join(seg.audio for seg in self.outbound_segments)
            self._save_wav(call_dir / "outbound_raw.wav", raw_outbound)

            # Save combined audio
            combined = self._mix_audio(bytes(self.inbound_audio), aligned_outbound)
            self._save_wav(call_dir / "combined.wav", combined)

        logger.info(f"Saved recording to {call_dir}")
        return call_dir

    def _save_wav(self, path: Path, pcm_data: bytes):
        """Save PCM data as WAV file (8kHz, 16-bit, mono)."""
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(8000)
            wav.writeframes(pcm_data)

    def _mix_audio(self, audio1: bytes, audio2: bytes) -> bytes:
        """Mix two audio tracks by averaging samples to prevent clipping."""
        # Ensure both are even length
        if len(audio1) % 2 == 1:
            audio1 = audio1[:-1]
        if len(audio2) % 2 == 1:
            audio2 = audio2[:-1]

        # Pad shorter audio
        max_len = max(len(audio1), len(audio2))
        # Ensure max_len is even
        max_len = max_len & ~1

        audio1 = audio1.ljust(max_len, b'\x00')
        audio2 = audio2.ljust(max_len, b'\x00')

        # Scale both tracks to 50% to prevent clipping when mixed
        audio1_scaled = audioop.mul(audio1, 2, 0.5)
        audio2_scaled = audioop.mul(audio2, 2, 0.5)

        # Mix by adding the scaled tracks
        return audioop.add(audio1_scaled, audio2_scaled, 2)
