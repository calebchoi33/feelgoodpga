#!/usr/bin/env python3
"""
Hospital Voice Bot - LiveKit Agent

Simulates patients calling hospital phone systems for QA testing.
"""

# SSL fix for macOS (must be before other imports)
import os
import ssl
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from livekit import api
from livekit.agents import (
    Agent,
    AgentSession,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
)
from livekit.plugins import deepgram, silero
from livekit.plugins.anthropic import llm as anthropic_llm

from scenarios import PatientScenario, SCENARIOS

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("patient-bot")

# Transcript directory
TRANSCRIPT_DIR = Path(__file__).parent / "transcripts"
TRANSCRIPT_DIR.mkdir(exist_ok=True)


class TranscriptLogger:
    """Logs conversation transcripts to file."""

    def __init__(self, scenario_name: str, room_name: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = scenario_name.replace(" ", "_").lower()
        self.filepath = TRANSCRIPT_DIR / f"{timestamp}_{safe_name}.txt"
        self.entries: list[str] = []

        # Write header
        self._write(f"Call Transcript: {scenario_name}")
        self._write(f"Room: {room_name}")
        self._write(f"Started: {datetime.now().isoformat()}")
        self._write("-" * 50)

    def _write(self, text: str):
        """Append line to transcript."""
        self.entries.append(text)
        with open(self.filepath, "a") as f:
            f.write(text + "\n")

    def log_user(self, text: str):
        """Log what the hospital system said (user input)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._write(f"[{timestamp}] HOSPITAL: {text}")
        logger.info(f"HOSPITAL: {text}")

    def log_agent(self, text: str):
        """Log what the bot said."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._write(f"[{timestamp}] PATIENT:  {text}")
        logger.info(f"PATIENT: {text}")

    def close(self):
        """Finalize transcript."""
        self._write("-" * 50)
        self._write(f"Ended: {datetime.now().isoformat()}")
        logger.info(f"Transcript saved: {self.filepath}")


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


class PatientAgent(Agent):
    """Voice agent that plays a patient calling a hospital."""

    def __init__(self, scenario: PatientScenario):
        details = "\n".join(f"- {k}: {v}" for k, v in scenario.details.items())

        super().__init__(
            instructions=PATIENT_PROMPT.format(
                name=scenario.name,
                dob=scenario.date_of_birth,
                goal=scenario.goal,
                details=f"Details:\n{details}" if details else "",
            )
        )
        self.scenario = scenario

    @function_tool
    async def hang_up(self) -> str:
        """End the call when the conversation is complete."""
        logger.info("Ending call")
        ctx = get_job_context()
        if ctx:
            await asyncio.sleep(1.0)  # Let final message play
            await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))
        return "Call ended."


async def entrypoint(ctx: RunContext):
    """Agent entrypoint - handles both inbound and outbound calls."""

    # Parse job metadata
    metadata = json.loads(ctx.job.metadata) if ctx.job.metadata else {}
    scenario_index = metadata.get("scenario_index", 0)
    phone_number = metadata.get("phone_number")
    sip_trunk_id = metadata.get("sip_trunk_id")

    if scenario_index >= len(SCENARIOS):
        logger.error(f"Invalid scenario index: {scenario_index}")
        return

    scenario = SCENARIOS[scenario_index]
    logger.info(f"Scenario: {scenario.name} | Goal: {scenario.goal}")

    # Set up transcript logging
    transcript = TranscriptLogger(scenario.name, ctx.room.name)

    # Create agent and session
    agent = PatientAgent(scenario)
    session = AgentSession(
        stt=deepgram.STT(model="nova-2"),
        llm=anthropic_llm.LLM(model="claude-sonnet-4-20250514"),
        tts=deepgram.TTS(model="aura-asteria-en"),
        vad=silero.VAD.load(),
    )

    @session.on("user_input_transcribed")
    def on_user_input(event):
        """Called when user (hospital) speech is transcribed."""
        if event.is_final:
            transcript.log_user(event.transcript)

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Place outbound call if phone number provided
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
        except api.TwirpError as e:
            logger.error(f"Call failed: {e.message}")
            await ctx.shutdown()
            return

    # Start the conversation
    await session.generate_reply(instructions="State why you're calling.")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="hospital-patient-bot",
        )
    )
