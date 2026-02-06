# Hospital Voice Bot

Automated voice bot for QA testing hospital phone systems using LiveKit Agents.

## Architecture

```
Twilio (SIP) → LiveKit Cloud → Deepgram (STT/TTS)
                    ↓
              Claude (LLM)
```

## Quick Start

```bash
# Install
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your keys

# Run agent
python agent.py dev

# Dispatch calls (in another terminal)
python dispatch.py -s 0  # Run scenario 0
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
python dispatch.py                 # Run all scenarios
python dispatch.py -s 0 1 -c 3     # Run scenarios 0,1 three times each
```

## Scenarios

11 test scenarios covering scheduling, rescheduling, cancellations, refills, and questions. See `scenarios.py`.

## Files

```
agent.py       - LiveKit voice agent
dispatch.py    - CLI to dispatch calls
scenarios.py   - Test scenarios
```

## Resources

- [LiveKit Agents](https://docs.livekit.io/agents/)
- [LiveKit Telephony](https://docs.livekit.io/agents/start/telephony/)
- [Twilio SIP Setup](https://docs.livekit.io/telephony/start/providers/twilio/)
