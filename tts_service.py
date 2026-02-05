"""
Text-to-Speech service using Deepgram.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)


class TTSService:
    """Text-to-speech using Deepgram API."""

    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not set")

        # Disable SSL verification (same issue as STT)
        self.client = httpx.AsyncClient(timeout=30.0, verify=False)

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to audio.

        Returns:
            Raw PCM audio bytes (8kHz, 16-bit, mono) ready for Twilio
        """
        url = "https://api.deepgram.com/v1/speak"
        params = {
            "model": "aura-asteria-en",  # Natural female voice
            "encoding": "linear16",
            "sample_rate": "8000",
        }

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "text/plain",
        }

        try:
            response = await self.client.post(url, params=params, headers=headers, content=text)
            response.raise_for_status()

            pcm_audio = response.content
            logger.info(f"TTS: {len(text)} chars -> {len(pcm_audio)} bytes")
            return pcm_audio

        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise

    async def close(self):
        await self.client.aclose()
