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
from litellm import acompletion, transcription

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE = os.getenv('TELEGRAM_PHONE', '')
GROQ_API_KEY=os.getenv('GROQ_API_KEY', '')
MODE = os.getenv('MODE', 'production').lower()  # test or production
FORMAT_TRANSCRIPTIONS = os.getenv('FORMAT_TRANSCRIPTIONS', 'true').lower() == 'true'

# Chats to skip (comma-separated list of chat IDs or @username)
# Messages in these chats will not be transcribed.
SKIP_CHATS = [
    c.strip() for c in os.getenv('SKIP_CHATS', '').split(',') if c.strip()
]

# Setup logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Create directory for temporary voice files
VOICE_DIR = Path('voice_messages')
VOICE_DIR.mkdir(exist_ok=True)

# Initialize Telegram client
client = TelegramClient('transcriber_session', API_ID, API_HASH)

# Track processed messages to avoid duplicates
processed_messages = set()


async def format_transcription(text: str) -> str:
    """Format transcription by adding appropriate paragraph breaks using LLM.

    Takes a wall-of-text transcription and uses Groq's Llama 3.1 8B Instant to intelligently
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

        response = await acompletion(
            model="groq/llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a text formatter. Your task is to adjust voice transcriptions to read in a clear and natural way, while preserving the original wording, sentence structure, etc. Add paragraph breaks (\\n\\n) to transcriptions at natural topic boundaries. Correct minor verbal artifacts such as 'um', 'like', 'yeah so uh'. Adjust punctuation to correct run-on sentences. Otherwise leave the text exactly as it was. Do not add any commentary, explanations, or markdown formatting. Return ONLY the formatted text."
                },
                {
                    "role": "user",
                    "content": f"Format this voice message transcription by adding paragraph breaks at natural topic boundaries:\n\n{text}"
                }
            ]
            # No max_completion_tokens - let the model stop naturally
        )

        # Log response details for debugging
        choices = getattr(response, 'choices', None)
        if choices is None and hasattr(response, 'get'):
            choices = response.get('choices', [])  # type: ignore[assignment]

        if not choices:
            logger.warning("Formatting returned no choices, using raw transcription.")
            return text

        first_choice = choices[0]
        finish_reason = getattr(first_choice, 'finish_reason', None)
        if finish_reason is None and isinstance(first_choice, dict):
            finish_reason = first_choice.get('finish_reason')

        message = getattr(first_choice, 'message', None)
        if message is None and isinstance(first_choice, dict):
            message = first_choice.get('message')

        if isinstance(message, dict):
            formatted = message.get('content')
        else:
            formatted = getattr(message, 'content', None)
        if formatted is None and isinstance(first_choice, dict):
            formatted = first_choice.get('content')

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


def _transcribe_with_groq(file_path: str):
    """Run the Groq Whisper transcription synchronously."""
    with open(file_path, 'rb') as audio_file:
        return transcription(
            model="groq/whisper-large-v3-turbo",
            file=audio_file
        )


async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio file using Groq Whisper API via LiteLLM."""
    try:
        logger.info(f"Transcribing {file_path}...")

        # Test mode: return mock transcription
        if MODE == 'test':
            logger.info("TEST MODE: Returning mock transcription")
            return "[TEST MODE] This is a mock transcription of the voice message."

        # Production mode: use real API
        transcript = await asyncio.to_thread(_transcribe_with_groq, file_path)

        if hasattr(transcript, 'text'):
            transcript_text = getattr(transcript, 'text', None)
        elif isinstance(transcript, dict):
            transcript_text = transcript.get('text')
        else:
            transcript_text = str(transcript)

        if transcript_text is None:
            transcript_text = ""
        else:
            transcript_text = str(transcript_text)

        logger.info("Transcription completed successfully")
        return transcript_text
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


def should_skip_chat(chat_id, chat) -> bool:
    """Check if a chat should be skipped based on SKIP_CHATS config.

    Supports matching by:
    - Numeric chat ID (e.g. '699561995' or '-1001234567890')
    - Username with @ prefix (e.g. '@channel_name')
    - Username without @ prefix (e.g. 'channel_name')
    - Chat title (exact match, case-insensitive)
    """
    if not SKIP_CHATS:
        return False

    chat_id_str = str(chat_id)
    username = (getattr(chat, 'username', None) or '').lower()
    title = (getattr(chat, 'title', None) or '').lower()

    # Also check first_name for DMs
    first_name = (getattr(chat, 'first_name', None) or '').lower()

    for skip in SKIP_CHATS:
        skip_lower = skip.lower()
        # Match by numeric chat ID
        if skip_lower == chat_id_str:
            return True
        # Match by @username or username
        if skip_lower.startswith('@'):
            if skip_lower[1:] == username:
                return True
        elif skip_lower == username:
            return True
        # Match by chat title (for groups/channels) or first_name (for DMs)
        if skip_lower == title or skip_lower == first_name:
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

    # Check if this chat is in the skip list
    if should_skip_chat(message.chat_id, chat):
        logger.info(f"Skipping voice message in '{chat_name}' (chat in skip list)")
        return

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
