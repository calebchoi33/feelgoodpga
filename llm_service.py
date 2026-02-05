"""
LLM service for generating patient responses using Anthropic Claude.
"""

import os
import logging
from anthropic import Anthropic
from scenarios import PatientScenario

logger = logging.getLogger(__name__)


def build_patient_prompt(scenario: PatientScenario) -> str:
    """Build system prompt for a patient calling a hospital."""
    details = "\n".join(f"- {k}: {v}" for k, v in scenario.details.items()) if scenario.details else ""

    return f"""You are playing the role of {scenario.name} in a demo/test call to a hospital phone system. Your date of birth is {scenario.date_of_birth}.

This is a TEST CALL for demonstration purposes. You know this is a demo and are completely comfortable with it. If the agent mentions this is a test line or demo, acknowledge it naturally and continue with your role.

Your goal for this demo: {scenario.goal}

Character details:
{details}

Instructions:
- Speak naturally like a real person on the phone
- Keep responses SHORT - 1-2 sentences max
- Be friendly and cooperative
- If they say "this is a test line" or similar, say something like "Yeah, I know - just testing things out" and continue
- Provide your name and date of birth when asked
- Stay focused on your goal
- If asked something you don't know, say you're not sure

Start by briefly stating why you're calling."""


class LLMService:
    """Generates patient responses using Claude."""

    def __init__(self, scenario: PatientScenario):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.client = Anthropic(api_key=api_key)
        self.system_prompt = build_patient_prompt(scenario)
        self.conversation: list[dict] = []

    async def generate_response(self, agent_text: str | None = None) -> str:
        """Generate the patient's response to what the agent said."""
        if agent_text:
            self.conversation.append({"role": "user", "content": agent_text})

        messages = self.conversation if self.conversation else [
            {"role": "user", "content": "(The call has connected. State why you're calling.)"}
        ]

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                system=self.system_prompt,
                messages=messages,
            )
            patient_response = response.content[0].text
            self.conversation.append({"role": "assistant", "content": patient_response})
            return patient_response

        except Exception as e:
            logger.error(f"LLM error: {e}")
            return "Sorry, can you repeat that?"
