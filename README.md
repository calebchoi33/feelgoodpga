# Hospital Voice Bot

An automated voice bot that makes test calls to hospital phone systems. The bot plays the role of different patients with various scenarios (scheduling appointments, requesting refills, asking questions) and records the conversations for quality analysis.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Twilio    │────▶│  FastAPI    │────▶│  Deepgram   │
│  (Calls)    │◀────│  Server     │◀────│  (STT/TTS)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Claude    │
                    │   (LLM)     │
                    └─────────────┘
```

- **Twilio**: Handles phone calls via bidirectional media streams
- **Deepgram**: Real-time speech-to-text and text-to-speech
- **Claude**: Generates natural patient responses based on scenarios
- **FastAPI**: WebSocket server for Twilio media streams

## Prerequisites

- Python 3.11+
- [ngrok](https://ngrok.com/) for exposing local server
- API keys for Twilio, Deepgram, and Anthropic

## Setup

1. Clone the repository and create a virtual environment:
   ```bash
   cd hospital-voice-bot
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy the example environment file and fill in your API keys:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

3. Start ngrok to expose your local server:
   ```bash
   ngrok http 8000
   ```

4. Update `WEBHOOK_BASE_URL` in `.env` with your ngrok URL.

## Usage

### Start the Server

```bash
python app.py
```

The server runs on `http://localhost:8000` with endpoints:
- `POST /voice` - Twilio webhook for call handling
- `WS /media-stream` - WebSocket for bidirectional audio
- `GET /health` - Health check
- `GET /call-status` - Current call status
- `POST /set-scenario/{index}` - Set active scenario

### Run Test Calls

```bash
# List all scenarios
python main.py --list

# Run all scenarios
python main.py

# Run specific scenarios
python main.py --scenario 0 1 2

# Run scenarios multiple times
python main.py --count 3
```

### Quick Single Call

```bash
python test_call.py
```

## Scenarios

The bot includes 11 test scenarios covering:
- **Scheduling**: New appointments, follow-ups
- **Rescheduling**: Changing existing appointments
- **Canceling**: Canceling appointments
- **Refills**: Medication refill requests
- **Questions**: Office hours, location, insurance

See [scenarios.py](scenarios.py) for the full list.

## Output

Call recordings are saved to `transcripts/<call_id>/`:
- `transcript.json` - Structured transcript with timestamps
- `transcript.txt` - Human-readable transcript
- `inbound.wav` - Audio from the hospital agent
- `outbound.wav` - Audio from the patient bot (aligned)
- `combined.wav` - Mixed audio of both parties
- `issues.json` - Quality issues found by analysis

After running calls, a `bug_report.md` is generated summarizing all issues.

## Project Structure

```
hospital-voice-bot/
├── app.py                 # FastAPI server & Twilio webhooks
├── main.py                # CLI for running test calls
├── conversation_manager.py # Orchestrates conversation flow
├── stt_service.py         # Deepgram speech-to-text
├── tts_service.py         # Deepgram text-to-speech
├── llm_service.py         # Claude response generation
├── recorder.py            # Audio recording & alignment
├── analyzer.py            # Conversation quality analysis
├── scenarios.py           # Patient test scenarios
├── twilio_client.py       # Twilio API client
├── test_call.py           # Quick test script
└── transcripts/           # Call recordings
```

## Configuration

Key environment variables:

| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Your Twilio phone number |
| `DEEPGRAM_API_KEY` | Deepgram API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `WEBHOOK_BASE_URL` | Public URL for Twilio webhooks |
| `HOSPITAL_PHONE_NUMBER` | Target phone number to call |
