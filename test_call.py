"""
Test script to make a call to the hospital test line.
"""

import os
from dotenv import load_dotenv
from twilio_client import TwilioClient

load_dotenv()

HOSPITAL_NUMBER = os.getenv("HOSPITAL_PHONE_NUMBER", "805-439-8008")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://unaffronted-cataracted-arianna.ngrok-free.dev")


def main():
    webhook_url = f"{WEBHOOK_BASE_URL}/voice"
    print(f"Calling {HOSPITAL_NUMBER}...")
    print(f"Webhook: {webhook_url}")

    client = TwilioClient()
    try:
        call_sid = client.make_call(HOSPITAL_NUMBER, webhook_url)
        print(f"Call initiated! SID: {call_sid}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
