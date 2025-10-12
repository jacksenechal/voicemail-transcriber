"""Tests for voice message detection logic."""

import pytest
from unittest.mock import Mock, MagicMock
from telethon.tl.types import (
    MessageMediaDocument,
    Document,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    MessageMediaPhoto
)

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transcriber import is_voice_message


@pytest.mark.asyncio
async def test_is_voice_message_with_voice_attribute():
    """Test that messages with voice attribute are detected."""
    # Create a mock message with voice message
    message = Mock()
    message.media = Mock(spec=MessageMediaDocument)

    # Create voice attribute
    voice_attr = Mock(spec=DocumentAttributeAudio)
    voice_attr.voice = True

    message.media.document = Mock(spec=Document)
    message.media.document.attributes = [voice_attr]

    result = await is_voice_message(message)
    assert result is True


@pytest.mark.asyncio
async def test_is_voice_message_with_regular_audio():
    """Test that regular audio files (not voice) are not detected."""
    message = Mock()
    message.media = Mock(spec=MessageMediaDocument)

    # Create audio attribute without voice flag
    audio_attr = Mock(spec=DocumentAttributeAudio)
    audio_attr.voice = False

    message.media.document = Mock(spec=Document)
    message.media.document.attributes = [audio_attr]

    result = await is_voice_message(message)
    assert result is False


@pytest.mark.asyncio
async def test_is_voice_message_with_no_media():
    """Test that messages without media return False."""
    message = Mock()
    message.media = None

    result = await is_voice_message(message)
    assert result is False


@pytest.mark.asyncio
async def test_is_voice_message_with_photo():
    """Test that photo messages are not detected as voice."""
    message = Mock()
    message.media = Mock(spec=MessageMediaPhoto)

    result = await is_voice_message(message)
    assert result is False


@pytest.mark.asyncio
async def test_is_voice_message_with_document_no_voice():
    """Test that documents without voice attribute return False."""
    message = Mock()
    message.media = Mock(spec=MessageMediaDocument)

    # Create filename attribute (not voice)
    filename_attr = Mock(spec=DocumentAttributeFilename)
    filename_attr.file_name = "document.pdf"

    message.media.document = Mock(spec=Document)
    message.media.document.attributes = [filename_attr]

    result = await is_voice_message(message)
    assert result is False


@pytest.mark.asyncio
async def test_is_voice_message_with_mixed_attributes():
    """Test detection with multiple attributes including voice."""
    message = Mock()
    message.media = Mock(spec=MessageMediaDocument)

    # Create multiple attributes including voice
    filename_attr = Mock(spec=DocumentAttributeFilename)
    filename_attr.file_name = "voice.ogg"

    voice_attr = Mock(spec=DocumentAttributeAudio)
    voice_attr.voice = True

    message.media.document = Mock(spec=Document)
    message.media.document.attributes = [filename_attr, voice_attr]

    result = await is_voice_message(message)
    assert result is True
