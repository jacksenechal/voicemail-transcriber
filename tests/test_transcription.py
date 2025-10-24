"""Tests for audio transcription functionality."""

import pytest
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.mark.asyncio
async def test_transcribe_audio_success():
    """Test successful transcription."""
    # Set MODE to production for this test
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber._transcribe_with_groq', return_value="This is a test transcription"):

        # Import the function after mocking
        from transcriber import transcribe_audio

        result = await transcribe_audio("test_audio.ogg")

        assert result == "This is a test transcription"


@pytest.mark.asyncio
async def test_transcribe_audio_api_error():
    """Test transcription with API error."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber._transcribe_with_groq', side_effect=Exception("API rate limit exceeded")):

        from transcriber import transcribe_audio

        result = await transcribe_audio("test_audio.ogg")

        assert "[Transcription failed:" in result
        assert "API rate limit exceeded" in result


@pytest.mark.asyncio
async def test_transcribe_audio_file_not_found():
    """Test transcription with missing file."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber._transcribe_with_groq', side_effect=FileNotFoundError("File not found")):

        from transcriber import transcribe_audio

        result = await transcribe_audio("nonexistent.ogg")

        assert "[Transcription failed:" in result
        assert "File not found" in result


@pytest.mark.asyncio
async def test_transcribe_audio_empty_response():
    """Test transcription with empty response."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber._transcribe_with_groq', return_value=""):

        from transcriber import transcribe_audio

        result = await transcribe_audio("test_audio.ogg")

        assert result == ""
