"""Tests for transcription formatting functionality."""

import pytest
from types import SimpleNamespace
from unittest.mock import patch

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
         patch('transcriber.completion') as mock_completion:

        # Mock LLM response with paragraph breaks
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
                    ),
                    finish_reason="stop"
                )
            ]
        )
        mock_completion.return_value = mock_response

        from transcriber import format_transcription

        text = "First paragraph. Second paragraph. Third paragraph. " * 10
        result = await format_transcription(text)

        # Should have paragraph breaks
        assert "\n\n" in result
        assert mock_completion.called


@pytest.mark.asyncio
async def test_format_transcription_api_error():
    """Test that formatting falls back to raw text on error."""
    with patch('transcriber.MODE', 'production'), \
         patch('transcriber.FORMAT_TRANSCRIPTIONS', True), \
         patch('transcriber.completion') as mock_completion:

        # Mock API error
        mock_completion.side_effect = Exception("API Error")

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
         patch('transcriber.completion') as mock_completion:

        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Formatted text."),
                    finish_reason="stop"
                )
            ]
        )
        mock_completion.return_value = mock_response

        from transcriber import format_transcription

        text = "Long transcription. " * 50
        await format_transcription(text)

        # Verify the call was made with correct parameters
        call_args = mock_completion.call_args
        kwargs = call_args.kwargs
        assert kwargs['model'] == 'gpt-5-nano'
        assert 'temperature' not in kwargs  # gpt-5-nano doesn't support temperature
        assert 'max_completion_tokens' not in kwargs  # No limit - let model stop naturally
        assert len(kwargs['messages']) == 2
        assert 'paragraph breaks' in kwargs['messages'][0]['content']
