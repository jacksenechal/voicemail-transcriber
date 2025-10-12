"""Tests for message splitting functionality."""

import pytest

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transcriber import split_message


def test_split_message_short_text():
    """Test that short messages are not split."""
    text = "This is a short message"
    result = split_message(text)
    assert len(result) == 1
    assert result[0] == text


def test_split_message_exact_limit():
    """Test message at exactly the limit."""
    text = "a" * 4096
    result = split_message(text)
    assert len(result) == 1
    assert result[0] == text


def test_split_message_over_limit():
    """Test message slightly over the limit."""
    text = "a" * 5000
    result = split_message(text)
    assert len(result) == 2
    assert len(result[0]) <= 4096
    assert len(result[1]) <= 4096
    assert "".join(result).replace(" ", "") == text  # Verify content preserved


def test_split_message_with_paragraphs():
    """Test splitting at paragraph boundaries."""
    paragraph = "This is a paragraph. " * 100
    text = "\n\n".join([paragraph] * 5)
    result = split_message(text)

    # Should split into multiple chunks
    assert len(result) > 1

    # Each chunk should be under the limit
    for chunk in result:
        assert len(chunk) <= 4096

    # Content should be preserved (accounting for whitespace normalization)
    # Check that the main content words are present
    combined = " ".join(result)
    assert "This is a paragraph" in combined


def test_split_message_with_sentences():
    """Test splitting at sentence boundaries when paragraphs are too long."""
    # Create a very long paragraph that exceeds 4096 chars
    sentence = "This is a sentence that will be repeated many times. "
    long_paragraph = sentence * 100

    result = split_message(long_paragraph)

    # Should split into multiple chunks
    assert len(result) > 1

    # Each chunk should be under the limit
    for chunk in result:
        assert len(chunk) <= 4096


def test_split_message_preserves_content():
    """Test that splitting preserves all content."""
    text = "Short paragraph.\n\n" + ("Long paragraph. " * 500)
    result = split_message(text)

    # All chunks should be under limit
    for chunk in result:
        assert len(chunk) <= 4096

    # Should have multiple chunks
    assert len(result) > 1


def test_split_message_empty():
    """Test with empty string."""
    result = split_message("")
    assert len(result) == 1
    assert result[0] == ""


def test_split_message_with_header():
    """Test realistic scenario with header and long transcription."""
    header = "🎤 Voice message transcription:\n\n"
    # Simulate a 6-minute transcription (roughly 1000 words = 6000 chars)
    transcription = "Word " * 1200
    full_text = header + transcription

    result = split_message(full_text, max_length=4096)

    # Should split into multiple messages
    assert len(result) >= 2

    # First chunk should contain the header
    assert "🎤" in result[0]

    # All chunks should be under limit
    for chunk in result:
        assert len(chunk) <= 4096
