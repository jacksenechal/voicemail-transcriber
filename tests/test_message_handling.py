"""Integration tests for message handling flow."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transcriber import VoiceMessageContext, processed_messages


@pytest.mark.asyncio
async def test_process_voice_message_success(mocker):
    """End-to-end happy path for process_voice_message."""
    processed_messages.clear()

    download_media = AsyncMock()
    reply = AsyncMock()

    with patch('transcriber.transcribe_audio', AsyncMock(return_value="Raw transcription")), \
         patch('transcriber.format_transcription', AsyncMock(return_value="Formatted transcription")):

        context = VoiceMessageContext(
            platform='telegram',
            message_id='1',
            chat_id='chat',
            sender_name='Alice',
            chat_name='Chat',
            download_media=download_media,
            reply=reply,
        )

        from transcriber import process_voice_message

        await process_voice_message(context)

    assert download_media.call_count == 1
    assert reply.call_count == 1
    assert reply.await_args.args[0].startswith("🎤 Voice message transcription")
    assert "Formatted transcription" in reply.await_args.args[0]


@pytest.mark.asyncio
async def test_process_voice_message_handles_long_text(mocker):
    """Ensure long transcriptions are split into multiple replies."""
    processed_messages.clear()
    download_media = AsyncMock()
    reply = AsyncMock()

    long_text = "Lorem ipsum " * 1000

    with patch('transcriber.transcribe_audio', AsyncMock(return_value=long_text)), \
         patch('transcriber.format_transcription', AsyncMock(side_effect=lambda text: text)):

        context = VoiceMessageContext(
            platform='telegram',
            message_id='2',
            chat_id='chat',
            sender_name='Alice',
            chat_name='Chat',
            download_media=download_media,
            reply=reply,
            max_message_length=200,
        )

        from transcriber import process_voice_message

        await process_voice_message(context)

    assert reply.call_count > 1
    for call in reply.await_args_list:
        assert len(call.args[0]) <= 200 + 10  # header space


@pytest.mark.asyncio
async def test_process_voice_message_duplicate_skipped():
    """Messages with duplicate processed keys are ignored."""
    processed_messages.clear()
    download_media = AsyncMock()
    reply = AsyncMock()

    context = VoiceMessageContext(
        platform='telegram',
        message_id='1',
        chat_id='chat',
        sender_name='Alice',
        chat_name='Chat',
        download_media=download_media,
        reply=reply,
    )

    from transcriber import process_voice_message

    with patch('transcriber.transcribe_audio', AsyncMock(return_value="Test")), \
         patch('transcriber.format_transcription', AsyncMock(return_value="Test")):
        await process_voice_message(context)
        await process_voice_message(context)

    assert download_media.call_count == 1
    assert reply.call_count == 1


@pytest.mark.asyncio
async def test_process_voice_message_transcription_failure():
    """When transcription fails the error is surfaced to the user."""
    processed_messages.clear()

    download_media = AsyncMock()
    reply = AsyncMock()

    context = VoiceMessageContext(
        platform='telegram',
        message_id='9',
        chat_id='chat',
        sender_name='Alice',
        chat_name='Chat',
        download_media=download_media,
        reply=reply,
    )

    from transcriber import process_voice_message

    with patch('transcriber.transcribe_audio', AsyncMock(return_value='[Transcription failed: boom]')):
        await process_voice_message(context)

    reply.assert_awaited_once()
    assert reply.await_args.args[0].startswith("❌ [Transcription failed")


@pytest.mark.asyncio
async def test_telegram_handler_creates_context():
    """Telegram handler should construct VoiceMessageContext and call processor."""
    with patch('transcriber.TelegramClient') as mock_telegram_client, \
         patch('transcriber.is_voice_message', AsyncMock(return_value=True)), \
         patch('transcriber.process_voice_message', AsyncMock()) as mock_process:

        mock_client = Mock()
        mock_client.add_event_handler = Mock()
        mock_telegram_client.return_value = mock_client

        from transcriber import TelegramVoiceTranscriber

        handler = TelegramVoiceTranscriber()

        message = Mock()
        message.id = 123
        message.chat_id = 456
        message.download_media = AsyncMock()
        message.reply = AsyncMock()
        message.file = Mock()
        message.file.ext = '.ogg'
        message.get_sender = AsyncMock(return_value=Mock(first_name='Bob'))

        event = Mock()
        event.message = message
        event.get_chat = AsyncMock(return_value=Mock(title='My Chat'))

        await handler._handle_new_message(event)

        assert mock_process.await_count == 1
        context = mock_process.await_args.args[0]
        assert context.platform == 'telegram'
        assert context.chat_name == 'My Chat'
        assert context.sender_name == 'Bob'


@pytest.mark.asyncio
async def test_telegram_handler_skips_non_voice():
    """Non voice messages should not trigger processing."""
    with patch('transcriber.TelegramClient') as mock_telegram_client, \
         patch('transcriber.is_voice_message', AsyncMock(return_value=False)), \
         patch('transcriber.process_voice_message', AsyncMock()) as mock_process:

        mock_client = Mock()
        mock_client.add_event_handler = Mock()
        mock_telegram_client.return_value = mock_client

        from transcriber import TelegramVoiceTranscriber

        handler = TelegramVoiceTranscriber()

        event = Mock()
        event.message = Mock()

        await handler._handle_new_message(event)

        assert mock_process.await_count == 0
