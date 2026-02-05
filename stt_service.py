"""
Speech-to-Text service using Deepgram WebSocket API.
"""

import os
import json
import asyncio
import logging
import ssl
from typing import Callable, Awaitable
import websockets

logger = logging.getLogger(__name__)

TranscriptCallback = Callable[[str, bool], Awaitable[None]]


class STTService:
    """Real-time speech-to-text using Deepgram."""

    DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not set")
        self.ws = None
        self.callback: TranscriptCallback | None = None
        self._receive_task: asyncio.Task | None = None

    async def start_stream(self, on_transcript: TranscriptCallback):
        """Open streaming connection to Deepgram."""
        self.callback = on_transcript

        params = "model=nova-2&encoding=mulaw&sample_rate=8000&channels=1&punctuate=true&interim_results=true&endpointing=200"
        url = f"{self.DEEPGRAM_URL}?{params}"

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        self.ws = await websockets.connect(url, additional_headers={"Authorization": f"Token {self.api_key}"}, ssl=ssl_context)
        logger.info("Deepgram connected")
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self):
        """Receive and process transcripts."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "Results":
                    alternatives = data.get("channel", {}).get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        if transcript and self.callback:
                            await self.callback(transcript, data.get("is_final", False))
                elif msg_type == "Metadata":
                    logger.info(f"Deepgram metadata: {data}")
                elif msg_type == "Error":
                    logger.error(f"Deepgram error: {data}")

        except websockets.ConnectionClosed as e:
            logger.warning(f"Deepgram connection closed: code={e.code}, reason={e.reason}")
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")

    async def send_audio(self, audio_bytes: bytes):
        """Send audio chunk to Deepgram."""
        if self.ws:
            try:
                await self.ws.send(audio_bytes)
            except websockets.ConnectionClosed as e:
                logger.warning(f"Deepgram connection closed while sending: code={e.code}, reason={e.reason}")
                self.ws = None  # Mark as disconnected

    async def stop_stream(self):
        """Close the Deepgram connection."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self.ws:
            await self.ws.close()
            self.ws = None
            self.callback = None
            logger.info("Deepgram disconnected")
