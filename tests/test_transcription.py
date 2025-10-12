"""Tests for audio transcription functionality."""

import pytest
from unittest.mock import Mock, patch, mock_open, AsyncMock
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.mark.asyncio
async def test_transcribe_audio_success(mocker):
    """Test successful transcription."""
    # Set MODE to production for this test
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock the transcription response
        mock_client.audio.transcriptions.create.return_value = "This is a test transcription"

        # Import the function after mocking
        from transcriber import transcribe_audio

        # Mock file operations
        mock_file_data = b"fake audio data"
        mocker.patch('builtins.open', mock_open(read_data=mock_file_data))

        result = await transcribe_audio("test_audio.ogg")

        assert result == "This is a test transcription"
        assert mock_client.audio.transcriptions.create.called


@pytest.mark.asyncio
async def test_transcribe_audio_api_error(mocker):
    """Test transcription with API error."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock API error
        mock_client.audio.transcriptions.create.side_effect = Exception("API rate limit exceeded")

        from transcriber import transcribe_audio

        mock_file_data = b"fake audio data"
        mocker.patch('builtins.open', mock_open(read_data=mock_file_data))

        result = await transcribe_audio("test_audio.ogg")

        assert "[Transcription failed:" in result
        assert "API rate limit exceeded" in result


@pytest.mark.asyncio
async def test_transcribe_audio_file_not_found(mocker):
    """Test transcription with missing file."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        from transcriber import transcribe_audio

        # Mock file not found error
        mocker.patch('builtins.open', side_effect=FileNotFoundError("File not found"))

        result = await transcribe_audio("nonexistent.ogg")

        assert "[Transcription failed:" in result
        assert "File not found" in result


@pytest.mark.asyncio
async def test_transcribe_audio_empty_response(mocker):
    """Test transcription with empty response."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock empty transcription
        mock_client.audio.transcriptions.create.return_value = ""

        from transcriber import transcribe_audio

        mock_file_data = b"fake audio data"
        mocker.patch('builtins.open', mock_open(read_data=mock_file_data))

        result = await transcribe_audio("test_audio.ogg")

        assert result == ""
