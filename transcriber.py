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
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE = os.getenv('TELEGRAM_PHONE', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
MODE = os.getenv('MODE', 'production').lower()  # test or production

# Setup logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# OpenAI client - initialized lazily
openai_client = None


def get_openai_client():
    """Get or create OpenAI client."""
    global openai_client
    if openai_client is None and MODE != 'test':
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return openai_client

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

        # Test mode: return mock transcription
        if MODE == 'test':
            logger.info("TEST MODE: Returning mock transcription")
            return "[TEST MODE] This is a mock transcription of the voice message."

        # Production mode: use real API
        client = get_openai_client()
        with open(file_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
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


def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split a long message into chunks that fit Telegram's message length limit.

    Telegram has a 4096 character limit per message. This function splits
    the text intelligently at paragraph/sentence boundaries when possible.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    # Try to split at paragraph boundaries first
    paragraphs = text.split('\n\n')

    for paragraph in paragraphs:
        # If adding this paragraph would exceed the limit
        if len(current_chunk) + len(paragraph) + 2 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # If a single paragraph is too long, split it by words
            if len(paragraph) > max_length:
                words = paragraph.split(' ')
                for word in words:
                    # If a single word is too long, split it forcefully
                    if len(word) > max_length:
                        for i in range(0, len(word), max_length):
                            chunks.append(word[i:i+max_length])
                        continue

                    # If adding this word would exceed limit
                    if len(current_chunk) + len(word) + 1 > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = word
                    else:
                        current_chunk += (" " if current_chunk else "") + word
            else:
                current_chunk = paragraph
        else:
            current_chunk += ("\n\n" if current_chunk else "") + paragraph

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


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

    file_path = None
    try:
        # Download voice message
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = VOICE_DIR / f"voice_{timestamp}_{message.id}.ogg"

        logger.info("Downloading voice message...")
        await message.download_media(file=str(file_path))
        logger.info(f"Downloaded to {file_path}")

        # Transcribe
        transcription = await transcribe_audio(str(file_path))
        logger.info(f"Transcription completed: {len(transcription)} characters")

        # Check if transcription failed
        if transcription.startswith("[Transcription failed:"):
            logger.error(f"Transcription failed: {transcription}")
            await message.reply(f"❌ {transcription}")
            return

        # Split into chunks if needed (Telegram has 4096 char limit)
        reply_header = "🎤 Voice message transcription:\n\n"
        full_text = reply_header + transcription
        message_chunks = split_message(full_text, max_length=4096)

        logger.info(f"Sending transcription in {len(message_chunks)} message(s)")

        # Send first message as a reply, rest as regular messages
        for i, chunk in enumerate(message_chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                # For continuation messages, add a header
                continuation = f"🎤 (continued {i+1}/{len(message_chunks)}):\n\n{chunk}"
                await message.reply(continuation)

        logger.info(f"Transcription sent successfully ({len(message_chunks)} message(s))")

    except Exception as e:
        logger.error(f"Error processing voice message: {e}", exc_info=True)
        try:
            error_msg = f"❌ Failed to transcribe voice message: {str(e)}"
            await message.reply(error_msg)
            logger.info("Error notification sent to user")
        except Exception as reply_error:
            logger.error(f"Failed to send error notification: {reply_error}", exc_info=True)

    finally:
        # Clean up audio file
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                logger.debug(f"Cleaned up audio file: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up audio file {file_path}: {cleanup_error}")


async def main():
    """Main function to start the bot."""
    logger.info("Starting Telegram Voice Transcriber...")

    if MODE == 'test':
        logger.info("Running in TEST mode - API calls will be mocked")
    else:
        logger.info("Running in PRODUCTION mode")

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
