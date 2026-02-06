#!/usr/bin/env python3
"""
Dispatch test calls to the hospital voice bot via LiveKit.

Usage:
    python dispatch.py --list              # List scenarios
    python dispatch.py --scenario 0        # Run scenario 0
    python dispatch.py                     # Run all scenarios
"""

import os
import sys
import json
import time
import asyncio
import argparse
from dotenv import load_dotenv

from livekit import api
from scenarios import SCENARIOS

load_dotenv()

# Configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
SIP_TRUNK_ID = os.getenv("LIVEKIT_SIP_TRUNK_ID")
HOSPITAL_NUMBER = os.getenv("HOSPITAL_PHONE_NUMBER", "+18054398008")

DELAY_BETWEEN_CALLS = 15


def check_config() -> list[str]:
    """Return list of missing required config variables."""
    required = {
        "LIVEKIT_URL": LIVEKIT_URL,
        "LIVEKIT_API_KEY": LIVEKIT_API_KEY,
        "LIVEKIT_API_SECRET": LIVEKIT_API_SECRET,
        "LIVEKIT_SIP_TRUNK_ID": SIP_TRUNK_ID,
    }
    return [name for name, value in required.items() if not value]


async def dispatch_call(scenario_index: int) -> bool:
    """Dispatch a single call. Returns True on success."""
    scenario = SCENARIOS[scenario_index]

    print(f"\n{'='*50}")
    print(f"[{scenario_index}] {scenario.name}")
    print(f"Goal: {scenario.goal}")
    print(f"{'='*50}")

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

        response = await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="hospital-patient-bot",
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
    """Run specified scenarios."""
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

    print(f"\n{'='*50}")
    print(f"Complete: {success}/{total} calls dispatched")
    print(f"{'='*50}")


def list_scenarios():
    """Print available scenarios."""
    print("Available scenarios:\n")
    for i, s in enumerate(SCENARIOS):
        print(f"  [{i}] {s.name}")
        print(f"      {s.scenario_type}: {s.goal}\n")


def main():
    parser = argparse.ArgumentParser(description="Dispatch hospital voice bot calls")
    parser.add_argument("-s", "--scenario", type=int, nargs="+", help="Scenario indices")
    parser.add_argument("-c", "--count", type=int, default=1, help="Repeat count")
    parser.add_argument("-l", "--list", action="store_true", help="List scenarios")
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return

    # Check config
    missing = check_config()
    if missing:
        print(f"ERROR: Missing config: {', '.join(missing)}")
        print("Check your .env file")
        sys.exit(1)

    # Determine scenarios
    indices = args.scenario if args.scenario else list(range(len(SCENARIOS)))
    for idx in indices:
        if idx < 0 or idx >= len(SCENARIOS):
            print(f"ERROR: Invalid scenario {idx}")
            sys.exit(1)

    print("Hospital Voice Bot - Dispatcher")
    print(f"Target: {HOSPITAL_NUMBER}")
    print(f"Scenarios: {len(indices)} x {args.count} = {len(indices) * args.count} calls")

    asyncio.run(run_scenarios(indices, args.count))


if __name__ == "__main__":
    main()
