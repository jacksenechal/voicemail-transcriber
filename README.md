# Telegram Voice Message Transcriber

An agent that monitors your Telegram account for voice messages in any chat (incoming or outgoing), transcribes them using Groq's Whisper Large V3 Turbo via LiteLLM, and replies with the transcription text.

## Features

- 🎤 Detects voice messages in all chats
- 🔄 Monitors both incoming and outgoing voice messages
- 🤖 Transcribes using Groq Whisper-Large-V3-Turbo (fast STT via LiteLLM)
- 📝 **Smart formatting**: Automatically adds paragraph breaks using Groq Llama 3.1 8B Instant for readability
- 🚫 **Skip chats**: Exclude specific chats from transcription (by ID, username, or title)
- 💬 Replies with transcription attached to the original voice message
- 📄 Handles long transcriptions by splitting into multiple messages
- 🔁 Runs persistently in the background
- 🛡️ Handles errors gracefully with logging

## Setup

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click on "API Development Tools"
4. Create a new application
5. Note down your `api_id` and `api_hash`

### 2. Get Groq API Key

1. Go to https://console.groq.com/keys
2. Create a new API key
3. Note it down (you won't be able to see it again)

### 3. Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Fill in your credentials:
- `TELEGRAM_API_ID`: Your Telegram API ID
- `TELEGRAM_API_HASH`: Your Telegram API hash
- `TELEGRAM_PHONE`: Your phone number (with country code, e.g., +123****7890)
- `GROQ_API_KEY`: Your Groq API key (used by LiteLLM)
- `MODE`: Set to `test` or `production` (default: `production`)
- `FORMAT_TRANSCRIPTIONS`: Set to `true` or `false` (default: `true`) - enables smart paragraph formatting
- `SKIP_CHATS`: Comma-separated list of chats to exclude from transcription. Supports:
  - Chat IDs (e.g., `699561995` for DMs, `-1001234567890` for groups/channels)
  - Usernames with `@` prefix (e.g., `@channel_name`)
  - Usernames without prefix (e.g., `channel_name`)
  - Chat titles (e.g., `Family Chat`)
  - Example: `SKIP_CHATS=699561995,-1001234567890,@channel_name,Family Chat`

### 5. Run Tests

Before running in production, validate the critical path with tests:

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_voice_detection.py

# Run with coverage report
pytest --cov=transcriber --cov-report=html
```

The test suite covers:
- ✅ Voice message detection logic
- ✅ Audio transcription with mocked API calls
- ✅ Message handling flow (download, transcribe, reply)
- ✅ Error handling and duplicate prevention
- ✅ Edge cases (non-voice messages, API failures)
- ✅ Skip chats (exclusion by ID, username, or title)

### 6. Run the Agent

#### Test Mode (Safe Testing with Real Telegram)

Test mode connects to your real Telegram account but uses mock transcriptions instead of calling the Groq API. This lets you validate the full flow without incurring API costs.

```bash
# Set MODE=test in your .env file, or:
MODE=test python transcriber.py
```

In test mode:
- ✅ Connects to real Telegram account
- ✅ Detects real voice messages
- ✅ Downloads voice files
- ✅ Replies with mock transcriptions
- ❌ Does NOT call Groq API (no costs)

You'll see `[TEST MODE]` prefix in transcription replies.

#### Production Mode (Live Transcription)

```bash
# Direct run
python transcriber.py

# Or explicitly set production mode
MODE=production python transcriber.py
```

**Run in tmux (recommended for persistence):**
```bash
# Start tmux session
tmux new -s transcriber

# Run the agent
python transcriber.py

# Detach from tmux: Press Ctrl+B, then D
# Reattach later: tmux attach -t transcriber
```

## Usage

Once running, the agent will:

1. Monitor all your Telegram chats
2. Detect any voice messages (sent or received)
3. Download and transcribe them using Groq Whisper Large V3 Turbo via LiteLLM
4. Reply to the original voice message with the transcription
5. Clean up temporary audio files

You'll see logs like:
```
[2025-10-11 22:15:30] INFO: Starting Telegram Voice Transcriber...
[2025-10-11 22:15:32] INFO: Logged in as: John (@john_doe)
[2025-10-11 22:15:32] INFO: Monitoring for voice messages in all chats...
[2025-10-11 22:15:45] INFO: Voice message detected in 'Family Chat' from Mom
[2025-10-11 22:15:46] INFO: Downloading voice message...
[2025-10-11 22:15:48] INFO: Transcribing...
[2025-10-11 22:15:52] INFO: Transcription sent successfully
```

## First Run

On first run, Telegram will send you a verification code:
1. Enter your phone number (already in .env)
2. You'll receive a code via Telegram
3. Enter the code when prompted
4. If you have 2FA enabled, enter your password

The session will be saved in `transcriber_session.session` for future runs.

## Stopping the Agent

- If running directly: Press `Ctrl+C`
- If running in tmux: Attach to session and press `Ctrl+C`, or kill the tmux session

## Troubleshooting

**"Invalid API ID/Hash"**: Check your credentials at https://my.telegram.org

**"Phone number invalid"**: Make sure to include country code (e.g., +1 for US)

**"Groq API error"**: Verify your API key and check you have credits

**"No voice messages detected"**: The agent only detects voice messages sent AFTER it starts running

## Testing Strategy

This project includes comprehensive tests to validate the critical path:

1. **Unit Tests** (`tests/test_voice_detection.py`): Tests voice message detection logic with various message types
2. **Transcription Tests** (`tests/test_transcription.py`): Tests Groq transcription integration with mocks
3. **Integration Tests** (`tests/test_message_handling.py`): Tests the full message handling flow

**Recommended workflow:**
1. Run `pytest` to validate all tests pass
2. Run in test mode (`MODE=test`) to verify end-to-end flow with your real Telegram account
3. Deploy to production mode (`MODE=production`) once validated

## Notes

- Voice messages are temporarily downloaded to `voice_messages/` and deleted after transcription
- The agent keeps track of processed messages to avoid duplicate transcriptions
- Groq Whisper Large V3 Turbo supports 100+ languages automatically
- **Costs**: Refer to the latest Groq pricing for Whisper-Large-V3-Turbo and Llama 3.1 8B Instant usage
- Use test mode to validate functionality without API costs
- **Smart formatting**: Uses Groq Llama 3.1 8B Instant (via LiteLLM) to intelligently add paragraph breaks at natural topic boundaries
  - Automatically enabled by default
  - Can be disabled with `FORMAT_TRANSCRIPTIONS=false`
  - Falls back to raw transcription if formatting fails
  - Skips transcriptions under 200 characters (already readable)
- **Long transcriptions**: Automatically splits messages over 4096 characters (Telegram's limit) into multiple replies
- **Comprehensive logging**: All errors, downloads, and transcriptions are logged with full context
- **Error handling**: Graceful fallbacks for API failures, network issues, and edge cases
- **Skip chats**: Use `SKIP_CHATS` in `.env` to exclude specific chats from transcription
  - Useful when another bot (e.g., Hermes) already handles transcription in certain chats
  - Matches by chat ID, `@username`, or chat title (case-insensitive)
  - Logged as `Skipping voice message in 'Chat Name' (chat in skip list)`

## License

MIT
