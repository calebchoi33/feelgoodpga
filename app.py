"""
Hospital Voice Bot - FastAPI Application
"""

import os
import json
import base64
import audioop
import logging
import uuid
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from stt_service import STTService
from llm_service import LLMService
from tts_service import TTSService
from conversation_manager import ConversationManager
from scenarios import SCENARIOS

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hospital Voice Bot")

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://unaffronted-cataracted-arianna.ngrok-free.dev")
WEBSOCKET_URL = WEBHOOK_BASE_URL.replace("https://", "wss://") + "/media-stream"

# Mutable state for scenario selection
class AppState:
    def __init__(self):
        self.active_scenario_index = 0
        self.last_call_id: str | None = None
        self.call_in_progress = False

    @property
    def active_scenario(self):
        return SCENARIOS[self.active_scenario_index]


app_state = AppState()


def encode_for_twilio(pcm_bytes: bytes) -> str:
    """Encode PCM audio to base64 mulaw for Twilio."""
    mulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)
    return base64.b64encode(mulaw_bytes).decode("utf-8")


class CallState:
    """Holds state for an active call."""
    def __init__(self):
        self.websocket: WebSocket | None = None
        self.stream_sid: str | None = None
        self.conversation: ConversationManager | None = None

    async def send_audio(self, pcm_bytes: bytes):
        """Send audio back to Twilio."""
        if self.websocket and self.stream_sid:
            payload = encode_for_twilio(pcm_bytes)
            message = {"event": "media", "streamSid": self.stream_sid, "media": {"payload": payload}}
            await self.websocket.send_json(message)

    async def cleanup(self):
        if self.conversation:
            await self.conversation.stop()
        self.websocket = None
        self.stream_sid = None
        self.conversation = None


active_call = CallState()


def build_twiml_stream(websocket_url: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{websocket_url}" />
  </Connect>
</Response>"""


@app.post("/voice")
async def voice_webhook(CallSid: str = Form(default="")):
    logger.info(f"Voice webhook: CallSid={CallSid}")
    return Response(content=build_twiml_stream(WEBSOCKET_URL), media_type="application/xml")


@app.post("/status")
async def status_webhook(CallSid: str = Form(default=""), CallStatus: str = Form(default="")):
    logger.info(f"Status: {CallStatus} | CallSid={CallSid}")
    return Response(content="OK", media_type="text/plain")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    await active_call.cleanup()
    active_call.websocket = websocket

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                active_call.stream_sid = data["start"]["streamSid"]
                call_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
                logger.info(f"Stream started: {active_call.stream_sid}, call_id: {call_id}")

                app_state.call_in_progress = True
                app_state.last_call_id = call_id
                scenario = app_state.active_scenario

                active_call.conversation = ConversationManager(
                    scenario=scenario,
                    stt=STTService(),
                    llm=LLMService(scenario),
                    tts=TTSService(),
                    audio_sender=active_call.send_audio,
                    call_id=call_id,
                )
                await active_call.conversation.start()

            elif event == "media":
                mulaw_bytes = base64.b64decode(data["media"]["payload"])
                if active_call.conversation:
                    # Record inbound audio and send to STT
                    active_call.conversation.add_inbound_audio(mulaw_bytes)
                    await active_call.conversation.stt.send_audio(mulaw_bytes)

            elif event == "stop":
                logger.info("Stream stopped")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    finally:
        await active_call.cleanup()
        app_state.call_in_progress = False


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/call-status")
async def call_status():
    """Get current call status for CLI coordination."""
    return {
        "in_progress": app_state.call_in_progress,
        "last_call_id": app_state.last_call_id,
        "scenario_index": app_state.active_scenario_index,
        "scenario_name": app_state.active_scenario.name,
    }


@app.post("/set-scenario/{index}")
async def set_scenario(index: int):
    """Set the active scenario for the next call."""
    if 0 <= index < len(SCENARIOS):
        app_state.active_scenario_index = index
        return {
            "success": True,
            "scenario_index": index,
            "scenario_name": SCENARIOS[index].name,
            "scenario_goal": SCENARIOS[index].goal,
        }
    return {"success": False, "error": f"Invalid index. Must be 0-{len(SCENARIOS)-1}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
