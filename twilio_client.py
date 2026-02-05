"""
Twilio client for making and managing phone calls.
"""

import os
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()


class TwilioClient:
    """Client for Twilio API calls."""

    def __init__(self):
        self.client = Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN"),
        )
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    def make_call(self, to_number: str, webhook_url: str) -> str:
        """Initiate an outbound call. Returns call SID."""
        call = self.client.calls.create(
            to=to_number,
            from_=self.phone_number,
            url=webhook_url,
            status_callback=webhook_url.replace("/voice", "/status"),
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
        return call.sid

    def get_status(self, call_sid: str) -> str:
        """Get call status."""
        try:
            return self.client.calls(call_sid).fetch().status
        except TwilioRestException as e:
            return f"error: {e.msg}"

    def end_call(self, call_sid: str) -> bool:
        """End an active call."""
        try:
            self.client.calls(call_sid).update(status="completed")
            return True
        except TwilioRestException:
            return False
