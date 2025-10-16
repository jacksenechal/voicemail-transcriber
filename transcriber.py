#!/usr/bin/env python3
"""Multi-platform voice message transcriber.

The original project supported Telegram voice message transcription.
This module generalises the message handling logic so that we can support
additional messaging platforms (Slack and Signal) while keeping the
transcription/formatting pipeline shared between them.

Each platform is responsible for detecting voice messages and providing a
``VoiceMessageContext`` describing how to download the audio and reply to the
user.  The shared ``process_voice_message`` coroutine performs the heavy
lifting: downloading the audio, sending it to Whisper, optionally formatting
the result, splitting long replies, and posting responses back to the
originating platform.

The Telegram integration remains event-driven using Telethon, while Slack uses
Socket Mode and Signal integrates with a running ``signal-cli`` REST API.
"""

import os
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional
from pathlib import Path
from datetime import datetime

import aiohttp
from dotenv import load_dotenv
from openai import OpenAI
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, DocumentAttributeAudio

try:
    from slack_sdk.socket_mode.aiohttp import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web.async_client import AsyncWebClient
except Exception:  # pragma: no cover - Slack is optional at runtime
    SocketModeClient = None  # type: ignore
    SocketModeRequest = None  # type: ignore
    SocketModeResponse = None  # type: ignore
    AsyncWebClient = None  # type: ignore

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE = os.getenv('TELEGRAM_PHONE', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

SLACK_APP_TOKEN = os.getenv('SLACK_APP_TOKEN', '')
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN', '')

SIGNAL_SERVICE_URL = os.getenv('SIGNAL_SERVICE_URL', 'http://localhost:8080').rstrip('/')
SIGNAL_ACCOUNT = os.getenv('SIGNAL_ACCOUNT', '')

PLATFORMS = [p.strip().lower() for p in os.getenv('PLATFORMS', 'telegram').split(',') if p.strip()]

MODE = os.getenv('MODE', 'production').lower()  # test or production
FORMAT_TRANSCRIPTIONS = os.getenv('FORMAT_TRANSCRIPTIONS', 'true').lower() == 'true'

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

# Track processed messages to avoid duplicates across all platforms
processed_messages: set[str] = set()


@dataclass(slots=True)
class VoiceMessageContext:
    """Context describing a voice message coming from any platform."""

    platform: str
    message_id: str
    chat_id: str
    sender_name: str
    chat_name: str
    download_media: Callable[[str], Awaitable[None]]
    reply: Callable[[str], Awaitable[None]]
    voice_file_suffix: str = 'ogg'
    max_message_length: int = 4096
    reply_header: str = "🎤 Voice message transcription:\n\n"
    continuation_header: str = "🎤 (continued):\n\n"
    metadata: dict = field(default_factory=dict)

    @property
    def processed_key(self) -> str:
        return f"{self.platform}:{self.chat_id}:{self.message_id}"


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

        client = get_openai_client()
        response = client.chat.completions.create(
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
            ]
            # No max_completion_tokens - let the model stop naturally
        )

        # Log response details for debugging
        finish_reason = response.choices[0].finish_reason
        formatted = response.choices[0].message.content

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
    """Split a long message into chunks that fit a messaging platform limit.

    Telegram historically limited messages to 4096 characters, while Slack and
    Signal allow larger payloads.  The helper takes the maximum payload size as
    an argument and splits at natural paragraph and word boundaries wherever
    possible so that the resulting messages remain readable.
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


async def process_voice_message(context: VoiceMessageContext) -> None:
    """Download, transcribe, and reply to a detected voice message."""

    if context.processed_key in processed_messages:
        logger.debug(
            "Skipping message %s from %s/%s - already processed",
            context.processed_key,
            context.platform,
            context.chat_name,
        )
        return

    processed_messages.add(context.processed_key)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = VOICE_DIR / f"{context.platform}_{timestamp}_{context.message_id}.{context.voice_file_suffix}"

    logger.info(
        "Voice message detected on %s in '%s' from %s",
        context.platform.capitalize(),
        context.chat_name,
        context.sender_name,
    )

    try:
        logger.info("Downloading voice message to %s", file_path)
        await context.download_media(str(file_path))
        logger.info("Download complete")

        transcription = await transcribe_audio(str(file_path))
        logger.info("Transcription completed (%d characters)", len(transcription))

        if transcription.startswith("[Transcription failed:"):
            logger.error("Transcription failed: %s", transcription)
            await context.reply(f"❌ {transcription}")
            return

        transcription = await format_transcription(transcription)

        if len(context.reply_header + transcription) <= context.max_message_length:
            await context.reply(context.reply_header + transcription)
            logger.info("Transcription sent successfully (single message)")
            return

        continuation_header = context.continuation_header
        max_header_len = max(len(context.reply_header), len(continuation_header))
        transcription_chunks = split_message(
            transcription,
            max_length=context.max_message_length - max_header_len,
        )

        logger.info("Sending transcription in %d message chunks", len(transcription_chunks))
        await context.reply(context.reply_header + transcription_chunks[0])
        for chunk in transcription_chunks[1:]:
            await context.reply(continuation_header + chunk)

        logger.info("Transcription sent successfully (%d messages)", len(transcription_chunks))

    except Exception as e:  # pragma: no cover - exercised via tests with mocks
        logger.error("Error processing voice message: %s", e, exc_info=True)
        try:
            await context.reply(f"❌ Failed to transcribe voice message: {str(e)}")
            logger.info("Error notification sent to user")
        except Exception as reply_error:
            logger.error("Failed to send error notification: %s", reply_error, exc_info=True)
    finally:
        if file_path.exists():
            try:
                file_path.unlink()
                logger.debug("Cleaned up audio file: %s", file_path)
            except Exception as cleanup_error:
                logger.warning("Failed to clean up audio file %s: %s", file_path, cleanup_error)


class TelegramVoiceTranscriber:
    """Telethon-based voice message handler for Telegram."""

    def __init__(self) -> None:
        self.client = TelegramClient('transcriber_session', API_ID, API_HASH)
        self.client.add_event_handler(self._handle_new_message, events.NewMessage())

    async def _handle_new_message(self, event) -> None:
        message = event.message

        if not await is_voice_message(message):
            return

        try:
            chat = await event.get_chat()
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown')
        except Exception:
            chat_name = "Unknown"

        try:
            sender = await message.get_sender()
            sender_name = getattr(sender, 'first_name', 'Unknown')
        except Exception:
            sender_name = "Unknown"

        voice_ext = 'ogg'
        try:
            file_attr = getattr(message, 'file', None)
            if file_attr and getattr(file_attr, 'ext', None):
                voice_ext = str(file_attr.ext).lstrip('.') or voice_ext
        except Exception:
            pass

        async def download_media(file_path: str) -> None:
            await message.download_media(file=file_path)

        async def reply(text: str) -> None:
            await message.reply(text)

        context = VoiceMessageContext(
            platform='telegram',
            message_id=str(message.id),
            chat_id=str(message.chat_id),
            sender_name=sender_name,
            chat_name=chat_name,
            download_media=download_media,
            reply=reply,
            voice_file_suffix=voice_ext,
            max_message_length=4096,
            reply_header="🎤 Voice message transcription:\n\n",
            continuation_header="🎤 (continued):\n\n",
            metadata={'event': event},
        )

        await process_voice_message(context)

    async def start(self) -> None:
        logger.info("Starting Telegram transcriber...")
        await self.client.start(phone=PHONE)

        me = await self.client.get_me()
        username = getattr(me, 'username', None)
        logger.info(
            "Logged into Telegram as %s (%s)",
            getattr(me, 'first_name', 'Unknown'),
            f"@{username}" if username else 'no username',
        )
        logger.info("Monitoring Telegram chats for voice messages...")
        await self.client.run_until_disconnected()


class SlackVoiceTranscriber:
    """Slack Socket Mode listener that transcribes audio attachments."""

    def __init__(self, app_token: str, bot_token: str) -> None:
        if SocketModeClient is None or AsyncWebClient is None or SocketModeResponse is None:
            raise RuntimeError("slack_sdk must be installed for Slack support")

        self.app_token = app_token
        self.bot_token = bot_token
        self.web_client = AsyncWebClient(token=bot_token)
        self.socket_client = SocketModeClient(app_token=app_token, web_client=self.web_client)
        self.socket_client.socket_mode_request_listeners.append(self._process_socket_mode_request)
        self._stop_event = asyncio.Event()
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _process_socket_mode_request(self, client: SocketModeClient, request: SocketModeRequest) -> None:
        if request.type == "disconnect":
            logger.warning("Slack Socket Mode disconnect received")
            self._stop_event.set()
            return

        if request.type != "events_api":
            return

        await client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))

        event = request.payload.get('event', {})
        if event.get('type') != 'message':
            return
        if event.get('bot_id'):
            return
        files = event.get('files') or []
        if not files:
            return

        for file_info in files:
            if not self._is_voice_file(file_info):
                continue
            await self._handle_voice_file(event, file_info)

    @staticmethod
    def _is_voice_file(file_info: dict) -> bool:
        mimetype = file_info.get('mimetype', '')
        filetype = (file_info.get('filetype') or '').lower()
        if mimetype.startswith('audio/'):
            return True
        return filetype in {'ogg', 'opus', 'mp3', 'm4a', 'wav'}

    async def _handle_voice_file(self, event: dict, file_info: dict) -> None:
        channel_id = event.get('channel') or 'unknown-channel'
        thread_ts = event.get('thread_ts') or event.get('ts')
        file_id = str(file_info.get('id', event.get('ts', 'unknown')))

        user_id = event.get('user')
        sender_name = user_id or 'Unknown'
        if user_id:
            try:
                user_info = await self.web_client.users_info(user=user_id)
                profile = user_info.get('user', {}).get('profile', {})
                sender_name = profile.get('real_name') or profile.get('display_name') or sender_name
            except Exception as exc:  # pragma: no cover - network failure path
                logger.warning("Failed to load Slack user info: %s", exc)

        chat_name = channel_id
        try:
            channel_info = await self.web_client.conversations_info(channel=channel_id)
            chat_name = channel_info.get('channel', {}).get('name') or chat_name
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning("Failed to load Slack channel info: %s", exc)

        download_url = file_info.get('url_private_download') or file_info.get('url_private')
        if not download_url:
            logger.warning("Slack file %s missing download URL", file_id)
            return

        filetype = (file_info.get('filetype') or 'ogg').lower()

        async def download_media(file_path: str) -> None:
            session = await self._ensure_session()
            headers = {"Authorization": f"Bearer {self.bot_token}"}
            async with session.get(download_url, headers=headers) as resp:
                resp.raise_for_status()
                with open(file_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(4096):
                        f.write(chunk)

        async def reply(text: str) -> None:
            await self.web_client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts,
            )

        context = VoiceMessageContext(
            platform='slack',
            message_id=f"{event.get('ts', '')}:{file_id}",
            chat_id=channel_id,
            sender_name=sender_name,
            chat_name=chat_name,
            download_media=download_media,
            reply=reply,
            voice_file_suffix=filetype,
            max_message_length=35000,
            reply_header="🎤 Voice message transcription (Slack):\n\n",
            continuation_header="🎤 (continued on Slack):\n\n",
            metadata={'event': event, 'file': file_info},
        )

        await process_voice_message(context)

    async def start(self) -> None:
        logger.info("Starting Slack transcriber...")
        await self.socket_client.connect()
        await self._stop_event.wait()

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        await self.web_client.close()


class SignalVoiceTranscriber:
    """Poll voice attachments from a signal-cli REST API instance."""

    def __init__(self, service_url: str, account: str) -> None:
        self.service_url = service_url.rstrip('/')
        self.account = account
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _receive_messages(self) -> list[dict]:
        session = await self._ensure_session()
        url = f"{self.service_url}/v1/receive/{self.account}"
        async with session.get(url, timeout=65) as resp:
            if resp.status == 204:
                return []
            resp.raise_for_status()
            payload = await resp.json()

        messages = payload.get('messages') or payload.get('envelopes') or []
        return messages

    @staticmethod
    def _is_voice_attachment(attachment: dict) -> bool:
        pointer = attachment.get('attachment') or attachment.get('attachmentPointer') or attachment
        content_type = (pointer.get('contentType') or '').lower()
        filename = pointer.get('fileName', '').lower()
        return (
            content_type.startswith('audio/')
            or filename.endswith('.ogg')
            or filename.endswith('.opus')
            or 'voice' in filename
        )

    async def _download_attachment(self, attachment: dict, file_path: str) -> None:
        pointer = attachment.get('attachment') or attachment.get('attachmentPointer') or attachment
        attachment_id = pointer.get('id')
        if attachment_id is None:
            raise ValueError('Signal attachment missing id')

        session = await self._ensure_session()
        url = f"{self.service_url}/v1/attachments/{attachment_id}"
        params = {'account': self.account}
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            with open(file_path, 'wb') as f:
                async for chunk in resp.content.iter_chunked(4096):
                    f.write(chunk)

    async def _send_message(self, recipient: Optional[str], group_id: Optional[str], text: str) -> None:
        session = await self._ensure_session()
        url = f"{self.service_url}/v1/send"
        payload: dict = {'message': text}
        if group_id:
            payload['groupId'] = group_id
        elif recipient:
            payload['recipient'] = recipient
        else:
            raise ValueError('Signal reply requires recipient or groupId')

        params = {'account': self.account}
        async with session.post(url, json=payload, params=params) as resp:
            resp.raise_for_status()

    async def _handle_envelope(self, envelope: dict) -> None:
        data_message = envelope.get('dataMessage')
        if not data_message:
            return

        attachments = data_message.get('attachments') or []
        if not attachments:
            return

        for attachment in attachments:
            if not self._is_voice_attachment(attachment):
                continue

            sender = envelope.get('source') or 'unknown-sender'
            sender_name = envelope.get('sourceName') or sender
            group_info = data_message.get('groupInfo') or {}
            group_id = group_info.get('groupId')
            chat_name = group_info.get('name') or group_id or sender
            chat_id = group_id or sender

            pointer = attachment.get('attachment') or attachment.get('attachmentPointer') or attachment
            file_name = pointer.get('fileName') or 'voice-message.ogg'
            suffix = file_name.rsplit('.', 1)[-1] if '.' in file_name else 'ogg'

            async def download_media(file_path: str) -> None:
                await self._download_attachment(attachment, file_path)

            async def reply(text: str) -> None:
                await self._send_message(sender if not group_id else None, group_id, text)

            context = VoiceMessageContext(
                platform='signal',
                message_id=str(pointer.get('id') or f"{sender}:{envelope.get('timestamp', '')}"),
                chat_id=str(chat_id),
                sender_name=sender_name,
                chat_name=str(chat_name),
                download_media=download_media,
                reply=reply,
                voice_file_suffix=suffix,
                max_message_length=4096,
                reply_header="🎤 Voice message transcription (Signal):\n\n",
                continuation_header="🎤 (Signal continued):\n\n",
                metadata={'envelope': envelope, 'attachment': attachment},
            )

            await process_voice_message(context)

    async def start(self) -> None:
        logger.info("Starting Signal transcriber against %s", self.service_url)
        while True:
            try:
                envelopes = await self._receive_messages()
                for envelope in envelopes:
                    await self._handle_envelope(envelope)
            except asyncio.CancelledError:  # pragma: no cover - cancellation path
                break
            except Exception as exc:  # pragma: no cover - network failure path
                logger.error("Signal polling error: %s", exc, exc_info=True)
                await asyncio.sleep(5)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


async def main() -> None:
    """Entry point that launches all configured platform listeners."""

    configured_platforms = [p for p in PLATFORMS if p]
    logger.info("Starting voice transcriber for platforms: %s", ', '.join(configured_platforms))

    if MODE == 'test':
        logger.info("Running in TEST mode - API calls will be mocked")
    else:
        logger.info("Running in PRODUCTION mode")

    tasks = []
    resources = []

    if 'telegram' in configured_platforms:
        if not API_ID or not API_HASH:
            logger.warning("Telegram platform requested but TELEGRAM_API_ID/HASH not configured")
        else:
            telegram = TelegramVoiceTranscriber()
            resources.append(telegram)
            tasks.append(asyncio.create_task(telegram.start()))

    if 'slack' in configured_platforms:
        if not SLACK_APP_TOKEN or not SLACK_BOT_TOKEN:
            logger.warning("Slack platform requested but SLACK_APP_TOKEN/SLACK_BOT_TOKEN missing")
        elif SocketModeClient is None:
            logger.warning("Slack platform requested but slack_sdk dependency is not installed")
        else:
            slack = SlackVoiceTranscriber(SLACK_APP_TOKEN, SLACK_BOT_TOKEN)
            resources.append(slack)
            tasks.append(asyncio.create_task(slack.start()))

    if 'signal' in configured_platforms:
        if not SIGNAL_ACCOUNT:
            logger.warning("Signal platform requested but SIGNAL_ACCOUNT missing")
        else:
            signal_transcriber = SignalVoiceTranscriber(SIGNAL_SERVICE_URL, SIGNAL_ACCOUNT)
            resources.append(signal_transcriber)
            tasks.append(asyncio.create_task(signal_transcriber.start()))

    if not tasks:
        raise RuntimeError("No messaging platforms configured. Check environment variables.")

    try:
        await asyncio.gather(*tasks)
    finally:
        # Give each resource the opportunity to close any lingering sessions
        for resource in resources:
            close = getattr(resource, 'close', None)
            if close:
                try:
                    await close()  # type: ignore[func-returns-value]
                except Exception as exc:  # pragma: no cover - cleanup path
                    logger.warning("Failed to close resource %s: %s", resource, exc)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
