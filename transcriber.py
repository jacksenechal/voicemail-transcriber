#!/usr/bin/env python3
"""
Telegram Voice Message Transcriber
Monitors all chats for voice messages and replies with transcriptions.
"""

import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, DocumentAttributeAudio
import openai

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE = os.getenv('TELEGRAM_PHONE')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Setup logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY

# Create directory for temporary voice files
VOICE_DIR = Path('voice_messages')
VOICE_DIR.mkdir(exist_ok=True)

# Initialize Telegram client
client = TelegramClient('transcriber_session', API_ID, API_HASH)

# Track processed messages to avoid duplicates
processed_messages = set()


async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio file using OpenAI Whisper API."""
    try:
        logger.info(f"Transcribing {file_path}...")
        with open(file_path, 'rb') as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        logger.info("Transcription completed successfully")
        return transcript
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return f"[Transcription failed: {str(e)}]"


async def is_voice_message(message) -> bool:
    """Check if a message contains a voice message."""
    if not message.media:
        return False

    if isinstance(message.media, MessageMediaDocument):
        document = message.media.document
        # Check for voice attribute or audio with voice flag
        for attr in document.attributes:
            if hasattr(attr, 'voice') and attr.voice:
                return True
            if isinstance(attr, DocumentAttributeAudio) and attr.voice:
                return True

    return False


@client.on(events.NewMessage)
async def handle_new_message(event):
    """Handle incoming messages and transcribe voice messages."""
    message = event.message

    # Skip if already processed
    msg_id = f"{message.chat_id}_{message.id}"
    if msg_id in processed_messages:
        return

    # Check if it's a voice message
    if not await is_voice_message(message):
        return

    # Mark as processed
    processed_messages.add(msg_id)

    # Get chat info for logging
    try:
        chat = await event.get_chat()
        chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown')
        sender = await message.get_sender()
        sender_name = getattr(sender, 'first_name', 'Unknown')
    except:
        chat_name = "Unknown"
        sender_name = "Unknown"

    logger.info(f"Voice message detected in '{chat_name}' from {sender_name}")

    try:
        # Download voice message
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = VOICE_DIR / f"voice_{timestamp}_{message.id}.ogg"

        logger.info("Downloading voice message...")
        await message.download_media(file=str(file_path))

        # Transcribe
        transcription = await transcribe_audio(str(file_path))

        # Reply with transcription
        reply_text = f"🎤 Voice message transcription:\n\n{transcription}"
        await message.reply(reply_text)

        logger.info(f"Transcription sent successfully")

        # Clean up audio file
        try:
            file_path.unlink()
        except:
            pass

    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        try:
            await message.reply(f"❌ Failed to transcribe voice message: {str(e)}")
        except:
            pass


async def main():
    """Main function to start the bot."""
    logger.info("Starting Telegram Voice Transcriber...")

    # Start client
    await client.start(phone=PHONE)

    me = await client.get_me()
    logger.info(f"Logged in as: {me.first_name} (@{me.username})")
    logger.info("Monitoring for voice messages in all chats...")
    logger.info("Press Ctrl+C to stop")

    # Keep the client running
    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
