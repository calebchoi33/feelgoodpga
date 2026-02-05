#!/usr/bin/env python3
"""
Main CLI entry point for running hospital voice bot test calls.
"""

import os
import sys
import time
import argparse
import requests
from dotenv import load_dotenv

from twilio_client import TwilioClient
from scenarios import SCENARIOS
from analyzer import generate_bug_report

load_dotenv()

HOSPITAL_NUMBER = os.getenv("HOSPITAL_PHONE_NUMBER", "805-439-8008")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://unaffronted-cataracted-arianna.ngrok-free.dev")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")

CALL_TIMEOUT = 600  # Max 10 minutes per call
POLL_INTERVAL = 2  # Check call status every 2 seconds
DELAY_BETWEEN_CALLS = 10  # Seconds between calls


def check_server_health() -> bool:
    """Check if the server is running."""
    try:
        resp = requests.get(f"{SERVER_URL}/health", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def set_scenario(index: int) -> bool:
    """Set the active scenario on the server."""
    try:
        resp = requests.post(f"{SERVER_URL}/set-scenario/{index}", timeout=5)
        data = resp.json()
        return data.get("success", False)
    except requests.RequestException as e:
        print(f"  Error setting scenario: {e}")
        return False


def get_call_status() -> dict:
    """Get current call status from server."""
    try:
        resp = requests.get(f"{SERVER_URL}/call-status", timeout=5)
        return resp.json()
    except requests.RequestException:
        return {"in_progress": False}


def wait_for_call_complete(initial_call_id: str | None, timeout: int = CALL_TIMEOUT) -> str | None:
    """Wait for a call to complete. Returns the call_id or None if timeout."""
    start_time = time.time()
    seen_new_call = False

    while time.time() - start_time < timeout:
        status = get_call_status()

        # Check if a new call started
        if status.get("last_call_id") and status.get("last_call_id") != initial_call_id:
            seen_new_call = True

        # If we saw a new call and it's no longer in progress, we're done
        if seen_new_call and not status.get("in_progress"):
            return status.get("last_call_id")

        time.sleep(POLL_INTERVAL)

    return None


def run_single_call(scenario_index: int, twilio_client: TwilioClient) -> dict:
    """Run a single test call for a scenario. Returns result dict."""
    scenario = SCENARIOS[scenario_index]
    result = {
        "scenario_index": scenario_index,
        "scenario_name": scenario.name,
        "success": False,
        "call_id": None,
        "error": None,
    }

    print(f"\n{'='*60}")
    print(f"Scenario {scenario_index + 1}/{len(SCENARIOS)}: {scenario.name}")
    print(f"Goal: {scenario.goal}")
    print(f"{'='*60}")

    # Set scenario on server
    print("  Setting scenario...")
    if not set_scenario(scenario_index):
        result["error"] = "Failed to set scenario on server"
        print(f"  ERROR: {result['error']}")
        return result

    # Get current call status (to detect when new call starts)
    initial_status = get_call_status()
    initial_call_id = initial_status.get("last_call_id")

    # Place the call
    print(f"  Placing call to {HOSPITAL_NUMBER}...")
    try:
        call_sid = twilio_client.make_call(HOSPITAL_NUMBER, f"{WEBHOOK_BASE_URL}/voice")
        print(f"  Call initiated: {call_sid}")
    except Exception as e:
        result["error"] = f"Failed to place call: {e}"
        print(f"  ERROR: {result['error']}")
        return result

    # Wait for call to complete
    print("  Waiting for call to complete...")
    call_id = wait_for_call_complete(initial_call_id)

    if call_id:
        result["success"] = True
        result["call_id"] = call_id
        print(f"  Call completed: {call_id}")
    else:
        result["error"] = "Call timed out"
        print(f"  ERROR: {result['error']}")

    return result


def run_all_calls(scenario_indices: list[int], count: int = 1) -> list[dict]:
    """Run calls for specified scenarios. Returns list of results."""
    results = []

    # Check server
    print("Checking server health...")
    if not check_server_health():
        print("ERROR: Server is not running. Start it with: python app.py")
        sys.exit(1)
    print("Server is healthy.\n")

    twilio_client = TwilioClient()

    total_calls = len(scenario_indices) * count
    call_num = 0

    for run in range(count):
        if count > 1:
            print(f"\n{'#'*60}")
            print(f"RUN {run + 1}/{count}")
            print(f"{'#'*60}")

        for scenario_index in scenario_indices:
            call_num += 1
            print(f"\n[Call {call_num}/{total_calls}]")

            result = run_single_call(scenario_index, twilio_client)
            results.append(result)

            # Delay between calls (except after last)
            if call_num < total_calls:
                print(f"\n  Waiting {DELAY_BETWEEN_CALLS}s before next call...")
                time.sleep(DELAY_BETWEEN_CALLS)

    return results


def print_summary(results: list[dict]):
    """Print summary of all calls."""
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"Calls completed: {len(successful)}/{len(results)}")

    if failed:
        print(f"\nFailed calls:")
        for r in failed:
            print(f"  - {r['scenario_name']}: {r['error']}")

    # Generate bug report
    print("\nGenerating bug report...")
    report_path = generate_bug_report()
    print(f"Bug report saved to: {report_path}")

    # Count issues
    try:
        with open(report_path) as f:
            content = f.read()
            if "Total issues" in content:
                for line in content.split("\n"):
                    if "Total issues" in line:
                        print(f"  {line.strip()}")
                        break
    except Exception:
        pass

    print(f"\nTranscripts saved to: transcripts/")


def main():
    parser = argparse.ArgumentParser(
        description="Run hospital voice bot test calls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run all scenarios once
  python main.py --scenario 0       # Run first scenario only
  python main.py --scenario 0 1 2   # Run scenarios 0, 1, and 2
  python main.py --count 3          # Run all scenarios 3 times each
  python main.py --list             # List all available scenarios
        """,
    )
    parser.add_argument(
        "--scenario", "-s",
        type=int,
        nargs="+",
        help="Scenario index(es) to run (0-based). Default: all scenarios",
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=1,
        help="Number of times to run each scenario. Default: 1",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available scenarios and exit",
    )

    args = parser.parse_args()

    # List scenarios
    if args.list:
        print("Available scenarios:\n")
        for i, s in enumerate(SCENARIOS):
            print(f"  {i}: {s.name}")
            print(f"     Type: {s.scenario_type}")
            print(f"     Goal: {s.goal}\n")
        return

    # Determine which scenarios to run
    if args.scenario is not None:
        scenario_indices = args.scenario
        # Validate indices
        for idx in scenario_indices:
            if idx < 0 or idx >= len(SCENARIOS):
                print(f"ERROR: Invalid scenario index {idx}. Must be 0-{len(SCENARIOS)-1}")
                sys.exit(1)
    else:
        scenario_indices = list(range(len(SCENARIOS)))

    print(f"Hospital Voice Bot - Test Runner")
    print(f"================================\n")
    print(f"Target: {HOSPITAL_NUMBER}")
    print(f"Scenarios: {len(scenario_indices)}")
    print(f"Runs per scenario: {args.count}")
    print(f"Total calls: {len(scenario_indices) * args.count}")

    # Run calls
    results = run_all_calls(scenario_indices, args.count)

    # Print summary
    print_summary(results)


if __name__ == "__main__":
    main()
