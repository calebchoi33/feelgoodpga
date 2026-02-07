#!/usr/bin/env python3
"""
Dispatch test calls to the hospital voice bot via LiveKit.

Usage:
    python dispatch.py -l              # List scenarios
    python dispatch.py -s 0            # Run scenario 0
    python dispatch.py -s 0 1 2        # Run scenarios 0, 1, 2
    python dispatch.py                 # Run all scenarios
    python dispatch.py -s 0 -c 3       # Run scenario 0 three times
"""

import argparse
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv
from livekit import api

from scenarios import SCENARIOS

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

AGENT_NAME = "hospital-patient-bot"
DELAY_BETWEEN_CALLS = 15

# LiveKit credentials (from .env)
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
SIP_TRUNK_ID = os.getenv("LIVEKIT_SIP_TRUNK_ID")
HOSPITAL_NUMBER = os.getenv("HOSPITAL_PHONE_NUMBER", "+18054398008")

REQUIRED_CONFIG = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_SIP_TRUNK_ID"]

# =============================================================================
# Dispatch Functions
# =============================================================================


def check_config() -> list[str]:
    """Return list of missing required config variables."""
    return [name for name in REQUIRED_CONFIG if not os.getenv(name)]


async def dispatch_call(scenario_index: int) -> bool:
    """Dispatch a single call to the hospital. Returns True on success."""
    scenario = SCENARIOS[scenario_index]

    print(f"\n{'=' * 50}")
    print(f"[{scenario_index}] {scenario.name}")
    print(f"Goal: {scenario.goal}")
    print(f"{'=' * 50}")

    lk = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )

    try:
        room_name = f"call-{scenario_index}-{int(time.time())}"
        metadata = json.dumps({
            "scenario_index": scenario_index,
            "phone_number": HOSPITAL_NUMBER,
            "sip_trunk_id": SIP_TRUNK_ID,
        })

        print(f"Dispatching to {HOSPITAL_NUMBER}...")

        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )
        print(f"Dispatched: room={room_name}")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False

    finally:
        await lk.aclose()


async def run_scenarios(indices: list[int], count: int = 1):
    """Run specified scenarios with optional repeat count."""
    total = len(indices) * count
    success = 0

    for run in range(count):
        for i, idx in enumerate(indices):
            call_num = run * len(indices) + i + 1
            print(f"\n[Call {call_num}/{total}]")

            if await dispatch_call(idx):
                success += 1

            if call_num < total:
                print(f"\nWaiting {DELAY_BETWEEN_CALLS}s...")
                await asyncio.sleep(DELAY_BETWEEN_CALLS)

    print(f"\n{'=' * 50}")
    print(f"Complete: {success}/{total} calls dispatched")
    print(f"{'=' * 50}")


# =============================================================================
# CLI
# =============================================================================


def list_scenarios():
    """Print available test scenarios."""
    print("Available scenarios:\n")
    for i, s in enumerate(SCENARIOS):
        print(f"  [{i}] {s.name}")
        print(f"      {s.scenario_type}: {s.goal}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Dispatch hospital voice bot calls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-s", "--scenario", type=int, nargs="+", help="Scenario indices to run")
    parser.add_argument("-c", "--count", type=int, default=1, help="Repeat count for each scenario")
    parser.add_argument("-l", "--list", action="store_true", help="List available scenarios")
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return

    # Validate config
    missing = check_config()
    if missing:
        print(f"ERROR: Missing config: {', '.join(missing)}")
        print("Check your .env file")
        sys.exit(1)

    # Validate scenario indices
    indices = args.scenario if args.scenario else list(range(len(SCENARIOS)))
    for idx in indices:
        if idx < 0 or idx >= len(SCENARIOS):
            print(f"ERROR: Invalid scenario index: {idx}")
            sys.exit(1)

    # Run
    print("Hospital Voice Bot - Dispatcher")
    print(f"Target: {HOSPITAL_NUMBER}")
    print(f"Scenarios: {len(indices)} x {args.count} = {len(indices) * args.count} calls")

    asyncio.run(run_scenarios(indices, args.count))


if __name__ == "__main__":
    main()
