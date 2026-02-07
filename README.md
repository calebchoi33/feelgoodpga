# Hospital Voice Bot

Automated voice bot for QA testing hospital phone systems using LiveKit Agents.

## Architecture

```
Twilio (SIP) → LiveKit Cloud → Deepgram (STT/TTS)
                    ↓
              Claude (LLM)
                    ↓
            Transcript Logs
```

## Quick Start

```bash
# Install
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your keys

# Run agent (Terminal 1)
python agent.py dev

# Dispatch calls (Terminal 2)
python dispatch.py -s 0
```

## Setup

### 1. Get API Keys

- [LiveKit Cloud](https://cloud.livekit.io) - URL, API key, API secret
- [Deepgram](https://console.deepgram.com) - API key
- [Anthropic](https://console.anthropic.com) - API key

### 2. Create SIP Trunk

```bash
# Create Twilio SIP trunk, then:
lk sip outbound create \
  --name "hospital-bot" \
  --address "your-trunk.pstn.twilio.com" \
  --auth-user "username" \
  --auth-pass "password" \
  --numbers "+1234567890"

# Get trunk ID
lk sip outbound list
```

Add `LIVEKIT_SIP_TRUNK_ID=ST_xxx` to your `.env`.

## Usage

```bash
# Start agent worker
python agent.py dev

# Dispatch calls
python dispatch.py -l              # List scenarios
python dispatch.py -s 0            # Run scenario 0
python dispatch.py -s 0 1 2        # Run multiple scenarios
python dispatch.py                 # Run all scenarios
python dispatch.py -s 0 -c 3       # Run scenario 0 three times
```

## Transcripts

Two-way conversation transcripts are automatically saved to `transcripts/`:

```
transcripts/
└── 20260206_141639_michael_thompson.txt
```

Example transcript:
```
Call Transcript: Michael Thompson
Room: call-0-1770416197
Started: 2026-02-06T14:16:39
--------------------------------------------------
[14:16:46] PATIENT:  Hi, I'm calling to schedule a new patient appointment...
[14:16:48] HOSPITAL: This call may be recorded for quality and training purposes.
[14:16:56] HOSPITAL: Am I speaking with Michael?
[14:16:59] PATIENT:  Yes, this is Michael Thompson...
[14:17:15] HOSPITAL: Can I have your date of birth?
[14:17:16] PATIENT:  Yes, my date of birth is March 22, 1985.
```

## Scenarios

11 test scenarios covering:
- Scheduling new appointments
- Rescheduling existing appointments
- Cancellations
- Prescription refills
- General questions

See `scenarios.py` for details.

## Files

```
agent.py       - LiveKit voice agent with transcript logging
dispatch.py    - CLI to dispatch test calls
scenarios.py   - Test scenario definitions
transcripts/   - Saved conversation transcripts
```

## Resources

- [LiveKit Agents](https://docs.livekit.io/agents/)
- [LiveKit Telephony](https://docs.livekit.io/agents/start/telephony/)
- [Twilio SIP Setup](https://docs.livekit.io/telephony/start/providers/twilio/)
