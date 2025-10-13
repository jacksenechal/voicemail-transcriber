"""Tests for transcription formatting functionality."""

import pytest
from unittest.mock import Mock, patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.mark.asyncio
async def test_format_transcription_disabled():
    """Test that formatting is skipped when disabled."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', False):

        from transcriber import format_transcription

        text = "This is a wall of text without any breaks it just keeps going on and on."
        result = await format_transcription(text)

        # Should return unformatted text
        assert result == text


@pytest.mark.asyncio
async def test_format_transcription_test_mode():
    """Test that formatting is skipped in test mode."""
    with patch('transcriber.MODE', 'test'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', True):

        from transcriber import format_transcription

        text = "This is a wall of text without any breaks it just keeps going on and on."
        result = await format_transcription(text)

        # Should return unformatted text in test mode
        assert result == text


@pytest.mark.asyncio
async def test_format_transcription_too_short():
    """Test that short transcriptions skip formatting."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', True):

        from transcriber import format_transcription

        text = "Short message."
        result = await format_transcription(text)

        # Should return unformatted text (too short)
        assert result == text


@pytest.mark.asyncio
async def test_format_transcription_success():
    """Test successful formatting with LLM."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', True), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock LLM response with paragraph breaks
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        mock_client.chat.completions.create.return_value = mock_response

        from transcriber import format_transcription

        text = "First paragraph. Second paragraph. Third paragraph. " * 10
        result = await format_transcription(text)

        # Should have paragraph breaks
        assert "\n\n" in result
        assert mock_client.chat.completions.create.called


@pytest.mark.asyncio
async def test_format_transcription_api_error():
    """Test that formatting falls back to raw text on error."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', True), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock API error
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        from transcriber import format_transcription

        text = "This is a long transcription that should be formatted but will fail and fallback to raw text. " * 10
        result = await format_transcription(text)

        # Should return original text on error
        assert result == text


@pytest.mark.asyncio
async def test_format_transcription_model_params():
    """Test that formatting uses correct model and parameters."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', True), \
         patch('transcriber.get_openai_client') as mock_get_client:

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Formatted text."
        mock_client.chat.completions.create.return_value = mock_response

        from transcriber import format_transcription

        text = "Long transcription. " * 50
        await format_transcription(text)

        # Verify the call was made with correct parameters
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]['model'] == 'gpt-5-nano'
        assert 'temperature' not in call_args[1]  # gpt-5-nano doesn't support temperature
        assert 'max_completion_tokens' not in call_args[1]  # No limit - let model stop naturally
        assert len(call_args[1]['messages']) == 2
        assert 'paragraph breaks' in call_args[1]['messages'][0]['content']
