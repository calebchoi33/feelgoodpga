"""
Conversation quality analyzer using LLM.
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from anthropic import Anthropic

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"


@dataclass
class Issue:
    issue_type: str
    severity: str  # "low" | "medium" | "high"
    description: str
    relevant_utterance: str


ANALYSIS_PROMPT = """You are a QA analyst reviewing a conversation between a hospital phone agent and a patient bot.

The patient bot's goal was: {goal}

Review the transcript below and identify any quality issues. Look for:
1. **hallucination** - Bot said incorrect/made-up information not in its persona
2. **misunderstanding** - Bot failed to understand what the agent said
3. **unnatural_phrasing** - Awkward or robotic language
4. **inappropriate_response** - Response doesn't fit the context
5. **goal_failure** - Bot failed to achieve its goal (scheduling, refill, etc.)
6. **repetition** - Bot repeated itself unnecessarily
7. **confusion** - Bot seemed confused or gave inconsistent answers

For each issue found, provide:
- issue_type: one of the types above
- severity: "low", "medium", or "high"
- description: brief explanation of the issue
- relevant_utterance: exact quote from the transcript

Respond with a JSON array of issues. If no issues found, return an empty array [].

Example response:
[
  {{
    "issue_type": "hallucination",
    "severity": "high",
    "description": "Bot claimed to have an appointment that wasn't part of its scenario",
    "relevant_utterance": "I already have an appointment scheduled for next Tuesday"
  }}
]

TRANSCRIPT:
{transcript}

Respond with ONLY the JSON array, no other text."""


class ConversationAnalyzer:
    """Analyzes conversation transcripts for quality issues."""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = Anthropic(api_key=api_key)

    def analyze(self, transcript_data: dict) -> list[Issue]:
        """Analyze a transcript and return list of issues."""
        # Format transcript for analysis
        transcript_text = self._format_transcript(transcript_data)
        goal = transcript_data.get("scenario", {}).get("goal", "Unknown")

        prompt = ANALYSIS_PROMPT.format(goal=goal, transcript=transcript_text)

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = response.content[0].text.strip()

            # Parse JSON response
            issues_data = json.loads(result_text)
            issues = [Issue(**issue) for issue in issues_data]
            logger.info(f"Analysis found {len(issues)} issues")
            return issues

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analysis response: {e}")
            return []
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return []

    def _format_transcript(self, transcript_data: dict) -> str:
        """Format transcript data into readable text."""
        lines = []
        for u in transcript_data.get("utterances", []):
            speaker = "AGENT" if u["speaker"] == "agent" else "PATIENT"
            lines.append(f"{speaker}: {u['text']}")
        return "\n".join(lines)

    def save_issues(self, call_dir: Path, issues: list[Issue]) -> Path:
        """Save issues to JSON file."""
        issues_path = call_dir / "issues.json"
        with open(issues_path, "w") as f:
            json.dump([asdict(i) for i in issues], f, indent=2)
        logger.info(f"Saved {len(issues)} issues to {issues_path}")
        return issues_path


def generate_bug_report() -> Path:
    """Generate aggregate bug report from all transcripts."""
    all_issues: list[dict] = []

    # Collect issues from all call directories
    for call_dir in TRANSCRIPTS_DIR.iterdir():
        if not call_dir.is_dir():
            continue
        issues_path = call_dir / "issues.json"
        if issues_path.exists():
            with open(issues_path) as f:
                issues = json.load(f)
                for issue in issues:
                    issue["call_id"] = call_dir.name
                all_issues.append(issues)

    # Flatten the list
    all_issues = [issue for call_issues in all_issues for issue in call_issues]

    if not all_issues:
        report = "# Bug Report\n\nNo issues found across all calls.\n"
    else:
        # Group by issue type
        by_type: dict[str, list[dict]] = {}
        for issue in all_issues:
            issue_type = issue["issue_type"]
            if issue_type not in by_type:
                by_type[issue_type] = []
            by_type[issue_type].append(issue)

        # Count by severity
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for issue in all_issues:
            severity_counts[issue["severity"]] += 1

        # Generate report
        lines = [
            "# Bug Report",
            "",
            "## Summary",
            "",
            f"- **Total issues**: {len(all_issues)}",
            f"- **High severity**: {severity_counts['high']}",
            f"- **Medium severity**: {severity_counts['medium']}",
            f"- **Low severity**: {severity_counts['low']}",
            "",
            "## Issues by Type",
            "",
        ]

        for issue_type, issues in sorted(by_type.items(), key=lambda x: -len(x[1])):
            lines.append(f"### {issue_type.replace('_', ' ').title()} ({len(issues)})")
            lines.append("")

            # Show up to 3 examples
            for issue in issues[:3]:
                severity_badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}[issue["severity"]]
                lines.append(f"**{severity_badge} {issue['severity'].upper()}** (Call: {issue['call_id']})")
                lines.append(f"> {issue['relevant_utterance']}")
                lines.append(f"")
                lines.append(f"{issue['description']}")
                lines.append("")

            if len(issues) > 3:
                lines.append(f"*...and {len(issues) - 3} more*")
                lines.append("")

        report = "\n".join(lines)

    # Save report
    report_path = TRANSCRIPTS_DIR / "bug_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    logger.info(f"Generated bug report at {report_path}")
    return report_path
