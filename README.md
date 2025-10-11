# Telegram Voice Message Transcriber

An agent that monitors your Telegram account for voice messages in any chat (incoming or outgoing), transcribes them using OpenAI's Whisper API, and replies with the transcription text.

## Features

- 🎤 Detects voice messages in all chats
- 🔄 Monitors both incoming and outgoing voice messages
- 🤖 Transcribes using OpenAI Whisper (best-in-class STT)
- 💬 Replies with transcription attached to the original voice message
- 🔁 Runs persistently in the background
- 🛡️ Handles errors gracefully with logging

## Setup

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click on "API Development Tools"
4. Create a new application
5. Note down your `api_id` and `api_hash`

### 2. Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
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
- `TELEGRAM_PHONE`: Your phone number (with country code, e.g., +1234567890)
- `OPENAI_API_KEY`: Your OpenAI API key

### 5. Run the Agent

**Direct run:**
```bash
python transcriber.py
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
3. Download and transcribe them using Whisper
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

**"OpenAI API error"**: Verify your API key and check you have credits

**"No voice messages detected"**: The agent only detects voice messages sent AFTER it starts running

## Notes

- Voice messages are temporarily downloaded to `voice_messages/` and deleted after transcription
- The agent keeps track of processed messages to avoid duplicate transcriptions
- Whisper API supports 100+ languages automatically
- Cost: ~$0.006 per minute of audio transcribed

## License

MIT
