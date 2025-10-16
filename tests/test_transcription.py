"""Tests for audio transcription functionality."""

import pytest
from types import SimpleNamespace
from unittest.mock import patch, mock_open

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.mark.asyncio
async def test_transcribe_audio_success(mocker):
    """Test successful transcription."""
    # Set MODE to production for this test
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.transcription') as mock_transcription:

        # Mock the transcription response
        mock_transcription.return_value = SimpleNamespace(text="This is a test transcription")

        # Import the function after mocking
        from transcriber import transcribe_audio

        # Mock file operations
        mock_file_data = b"fake audio data"
        mocker.patch('builtins.open', mock_open(read_data=mock_file_data))

        result = await transcribe_audio("test_audio.ogg")

        assert result == "This is a test transcription"
        assert mock_transcription.called


@pytest.mark.asyncio
async def test_transcribe_audio_api_error(mocker):
    """Test transcription with API error."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.transcription') as mock_transcription:

        # Mock API error
        mock_transcription.side_effect = Exception("API rate limit exceeded")

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
         patch('transcriber.transcription') as mock_transcription:

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
         patch('transcriber.transcription') as mock_transcription:

        # Mock empty transcription
        mock_transcription.return_value = SimpleNamespace(text="")

        from transcriber import transcribe_audio

        mock_file_data = b"fake audio data"
        mocker.patch('builtins.open', mock_open(read_data=mock_file_data))

        result = await transcribe_audio("test_audio.ogg")

        assert result == ""
