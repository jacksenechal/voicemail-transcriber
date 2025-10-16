"""Integration tests for message handling flow."""

import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from telethon.tl.types import MessageMediaDocument, Document, DocumentAttributeAudio

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.mark.asyncio
async def test_handle_new_message_with_voice(mocker):
    """Test full flow: voice message detection, download, transcription, and reply."""
    with patch('transcriber.transcription') as mock_transcription, \
         patch('transcriber.TelegramClient') as mock_telegram_client:

        # Setup transcription mock
        mock_transcription.return_value = SimpleNamespace(text="Test transcription")

        # Setup Telegram client mock
        mock_client = Mock()
        mock_telegram_client.return_value = mock_client

        # Import after mocking
        from transcriber import handle_new_message, processed_messages
        processed_messages.clear()

        # Create mock event with voice message
        event = Mock()
        message = Mock()
        message.id = 12345
        message.chat_id = 67890

        # Setup voice message media
        message.media = Mock(spec=MessageMediaDocument)
        voice_attr = Mock(spec=DocumentAttributeAudio)
        voice_attr.voice = True
        message.media.document = Mock(spec=Document)
        message.media.document.attributes = [voice_attr]

        event.message = message

        # Mock chat and sender info
        chat = Mock()
        chat.title = "Test Chat"
        event.get_chat = AsyncMock(return_value=chat)

        sender = Mock()
        sender.first_name = "John"
        message.get_sender = AsyncMock(return_value=sender)

        # Mock file operations
        message.download_media = AsyncMock()
        message.reply = AsyncMock()

        # Mock file operations
        mocker.patch('builtins.open', mocker.mock_open(read_data=b"fake audio"))
        mocker.patch('pathlib.Path.unlink')

        # Call handler
        await handle_new_message(event)

        # Verify the flow
        assert message.download_media.called
        assert message.reply.called

        # Check reply content
        reply_call = message.reply.call_args
        reply_text = reply_call[0][0]
        assert "Test transcription" in reply_text
        assert "🎤" in reply_text


@pytest.mark.asyncio
async def test_handle_new_message_duplicate_prevention(mocker):
    """Test that duplicate messages are not processed."""
    with patch('transcriber.transcription') as mock_transcription, \
         patch('transcriber.TelegramClient') as mock_telegram_client:

        from transcriber import handle_new_message, processed_messages

        # Pre-populate processed messages
        processed_messages.clear()
        processed_messages.add("67890_12345")

        # Create mock event
        event = Mock()
        message = Mock()
        message.id = 12345
        message.chat_id = 67890

        # Setup voice message
        message.media = Mock(spec=MessageMediaDocument)
        voice_attr = Mock(spec=DocumentAttributeAudio)
        voice_attr.voice = True
        message.media.document = Mock(spec=Document)
        message.media.document.attributes = [voice_attr]

        event.message = message
        message.reply = AsyncMock()

        # Call handler
        await handle_new_message(event)

        # Verify no reply was sent (message was skipped)
        assert not message.reply.called


@pytest.mark.asyncio
async def test_handle_new_message_non_voice(mocker):
    """Test that non-voice messages are ignored."""
    with patch('transcriber.transcription') as mock_transcription, \
         patch('transcriber.TelegramClient') as mock_telegram_client:

        from transcriber import handle_new_message, processed_messages
        processed_messages.clear()

        # Create mock event with text message (no media)
        event = Mock()
        message = Mock()
        message.id = 12345
        message.chat_id = 67890
        message.media = None

        event.message = message
        message.reply = AsyncMock()

        # Call handler
        await handle_new_message(event)

        # Verify no reply was sent
        assert not message.reply.called


@pytest.mark.asyncio
async def test_handle_new_message_transcription_error(mocker):
    """Test error handling when transcription fails."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.transcription') as mock_transcription, \
         patch('transcriber.TelegramClient') as mock_telegram_client:

        # Setup transcription to raise error
        mock_transcription.side_effect = Exception("API Error")

        from transcriber import handle_new_message, processed_messages
        processed_messages.clear()

        # Create mock event with voice message
        event = Mock()
        message = Mock()
        message.id = 12345
        message.chat_id = 67890

        message.media = Mock(spec=MessageMediaDocument)
        voice_attr = Mock(spec=DocumentAttributeAudio)
        voice_attr.voice = True
        message.media.document = Mock(spec=Document)
        message.media.document.attributes = [voice_attr]

        event.message = message

        # Mock required methods
        chat = Mock()
        chat.title = "Test Chat"
        event.get_chat = AsyncMock(return_value=chat)

        sender = Mock()
        sender.first_name = "John"
        message.get_sender = AsyncMock(return_value=sender)

        message.download_media = AsyncMock()
        message.reply = AsyncMock()

        mocker.patch('builtins.open', mocker.mock_open(read_data=b"fake audio"))
        mocker.patch('pathlib.Path.unlink')

        # Call handler
        await handle_new_message(event)

        # Verify error message was sent
        assert message.reply.called
        reply_text = message.reply.call_args[0][0]
        assert "[Transcription failed:" in reply_text
