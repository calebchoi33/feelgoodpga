"""
Patient test scenarios for the hospital voice bot.
"""

from dataclasses import dataclass, field
from typing import Literal

ScenarioType = Literal["scheduling", "rescheduling", "canceling", "refill", "question"]


@dataclass
class PatientScenario:
    """A patient calling scenario for testing."""
    name: str
    date_of_birth: str  # Format: "January 15, 1980"
    scenario_type: ScenarioType
    goal: str
    details: dict = field(default_factory=dict)


SCENARIOS: list[PatientScenario] = [
    # Scheduling
    PatientScenario(
        name="Michael Thompson",
        date_of_birth="March 22, 1985",
        scenario_type="scheduling",
        goal="Schedule a new patient appointment for a general checkup",
        details={"preferred_time": "morning", "reason": "annual physical exam"},
    ),
    PatientScenario(
        name="Sarah Chen",
        date_of_birth="July 8, 1992",
        scenario_type="scheduling",
        goal="Schedule an appointment for persistent headaches",
        details={"preferred_time": "afternoon", "urgency": "soon as possible"},
    ),
    PatientScenario(
        name="Robert Williams",
        date_of_birth="November 30, 1958",
        scenario_type="scheduling",
        goal="Schedule a follow-up appointment after lab work",
        details={"reason": "discuss cholesterol lab results"},
    ),
    # Rescheduling
    PatientScenario(
        name="Jennifer Garcia",
        date_of_birth="February 14, 1979",
        scenario_type="rescheduling",
        goal="Reschedule existing appointment to a different day",
        details={"current_appointment": "next Tuesday at 2pm", "reason": "work conflict"},
    ),
    # Canceling
    PatientScenario(
        name="David Park",
        date_of_birth="September 3, 1988",
        scenario_type="canceling",
        goal="Cancel upcoming appointment",
        details={"reason": "feeling better"},
    ),
    # Refills
    PatientScenario(
        name="Patricia Johnson",
        date_of_birth="April 17, 1965",
        scenario_type="refill",
        goal="Request refill for blood pressure medication",
        details={"medication": "Lisinopril 10mg", "pharmacy": "CVS"},
    ),
    PatientScenario(
        name="James Wilson",
        date_of_birth="December 5, 1972",
        scenario_type="refill",
        goal="Request refill for allergy medication",
        details={"medication": "Zyrtec", "pharmacy": "Walgreens"},
    ),
    # Questions
    PatientScenario(
        name="Emily Rodriguez",
        date_of_birth="June 25, 1995",
        scenario_type="question",
        goal="Ask about office hours",
        details={"question": "Are you open on Saturdays?"},
    ),
    PatientScenario(
        name="Thomas Anderson",
        date_of_birth="August 12, 1983",
        scenario_type="question",
        goal="Ask about office location",
        details={"question": "What is your address?"},
    ),
    PatientScenario(
        name="Maria Santos",
        date_of_birth="January 29, 1976",
        scenario_type="question",
        goal="Ask about insurance",
        details={"insurance": "Blue Cross Blue Shield"},
    ),
    # Edge case
    PatientScenario(
        name="Harold Miller",
        date_of_birth="October 10, 1950",
        scenario_type="question",
        goal="Vague request that needs clarification",
        details={"style": "rambling, unclear"},
    ),
]


def get_scenario(name: str) -> PatientScenario | None:
    """Find a scenario by patient name."""
    for s in SCENARIOS:
        if s.name.lower() == name.lower():
            return s
    return None
