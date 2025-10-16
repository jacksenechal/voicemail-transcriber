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
from litellm import completion, transcription

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE = os.getenv('TELEGRAM_PHONE', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
MODE = os.getenv('MODE', 'production').lower()  # test or production
FORMAT_TRANSCRIPTIONS = os.getenv('FORMAT_TRANSCRIPTIONS', 'true').lower() == 'true'

# Setup logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def _get_api_key() -> str | None:
    """Return the configured API key, or None if not provided."""
    return OPENAI_API_KEY or None

# Create directory for temporary voice files
VOICE_DIR = Path('voice_messages')
VOICE_DIR.mkdir(exist_ok=True)

# Initialize Telegram client (fallback to no-op when credentials missing)


class NoopTelegramClient:
    """Minimal stub used when Telegram credentials are unavailable."""

    def on(self, *args, **kwargs):  # noqa: D401 - simple passthrough decorator
        """Return the original function without registering any handlers."""

        def decorator(func):
            return func

        return decorator

    async def start(self, *args, **kwargs):
        raise RuntimeError("Telegram credentials are not configured.")

    async def get_me(self):
        raise RuntimeError("Telegram credentials are not configured.")

    async def run_until_disconnected(self):
        raise RuntimeError("Telegram credentials are not configured.")


if API_ID and API_HASH:
    client = TelegramClient('transcriber_session', API_ID, API_HASH)
else:
    logger.warning(
        "Telegram credentials missing. Using no-op Telegram client - real bot functionality is disabled."
    )
    client = NoopTelegramClient()

# Track processed messages to avoid duplicates
processed_messages = set()


async def format_transcription(text: str) -> str:
    """Format transcription by adding appropriate paragraph breaks using LLM.

    Takes a wall-of-text transcription and uses GPT-4o-mini to intelligently
    add paragraph breaks at natural topic boundaries.
    """
    try:
        logger.info(f"Formatting transcription ({len(text)} chars)...")

        # Test mode: return unformatted
        if MODE == 'test':
            logger.info("TEST MODE: Skipping formatting")
            return text

        # Skip formatting if disabled
        if not FORMAT_TRANSCRIPTIONS:
            logger.info("Formatting disabled, returning raw transcription")
            return text

        # Skip if transcription is already short (likely already readable)
        if len(text) < 200:
            logger.info("Transcription too short to need formatting")
            return text

        response = completion(
            model="gpt-5-nano",
            messages=[
                {
                    "role": "system",
                    "content": "You are a text formatter. Your task is to adjust voice transcriptions to read in a clear and natural way, while preserving the original wording, sentence structure, etc. Add paragraph breaks (\\n\\n) to transcriptions at natural topic boundaries. Correct minor verbal artifacts such as 'um', 'like', 'yeah so uh'. Adjust punctuation to correct run-on sentences. Otherwise leave the text exactly as it was. Do not add any commentary, explanations, or markdown formatting. Return ONLY the formatted text."
                },
                {
                    "role": "user",
                    "content": f"Format this voice message transcription by adding paragraph breaks at natural topic boundaries:\n\n{text}"
                }
            ],
            api_key=_get_api_key()
            # No max_completion_tokens - let the model stop naturally
        )

        # Log response details for debugging
        first_choice = response.choices[0]
        finish_reason = getattr(first_choice, "finish_reason", None)
        message = getattr(first_choice, "message", None)
        formatted = getattr(message, "content", None) if message is not None else None

        logger.info(f"Formatting API response - finish_reason: {finish_reason}, content length: {len(formatted) if formatted else 0}")

        # Handle empty or None response
        if not formatted or not formatted.strip():
            logger.warning(
                f"Formatting returned empty/null content (finish_reason: {finish_reason}). "
                f"This might be a model issue. Using raw transcription."
            )
            return text

        formatted = formatted.strip()
        logger.info(f"Formatting completed ({len(formatted)} chars)")
        return formatted

    except Exception as e:
        logger.warning(f"Formatting failed, returning raw transcription: {e}")
        return text  # Fallback to unformatted on error


async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio file using OpenAI Whisper API."""
    try:
        logger.info(f"Transcribing {file_path}...")

        # Test mode: return mock transcription
        if MODE == 'test':
            logger.info("TEST MODE: Returning mock transcription")
            return "[TEST MODE] This is a mock transcription of the voice message."

        # Production mode: use real API
        with open(file_path, 'rb') as audio_file:
            transcript_response = transcription(
                model="whisper-1",
                file=audio_file,
                response_format="text",
                api_key=_get_api_key()
            )

        transcript = getattr(transcript_response, "text", transcript_response)
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

        # Format transcription with paragraph breaks
        transcription = await format_transcription(transcription)

        # Split into chunks if needed (Telegram has 4096 char limit)
        reply_header = "🎤 Voice message transcription:\n\n"
        if len(reply_header + transcription) <= 4096:
            # Short message, send as single reply
            await message.reply(reply_header + transcription)
            logger.info("Transcription sent successfully (1 message)")
        else:
            # Long message, need to split
            # We need to reserve space for headers:
            # - First chunk needs space for reply_header
            # - Subsequent chunks need space for continuation_header
            continuation_header = "🎤 (continued):\n\n"
            max_header_len = max(len(reply_header), len(continuation_header))

            # Split transcription into chunks, reserving space for the longest header
            transcription_chunks = split_message(transcription, max_length=4096 - max_header_len)

            logger.info(f"Sending transcription in {len(transcription_chunks)} message(s)")

            # Send first message with main header
            first_message = reply_header + transcription_chunks[0]
            await message.reply(first_message)

            # Send continuation messages
            for i in range(1, len(transcription_chunks)):
                continuation = continuation_header + transcription_chunks[i]
                await message.reply(continuation)

            logger.info(f"Transcription sent successfully ({len(transcription_chunks)} message(s))")

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
