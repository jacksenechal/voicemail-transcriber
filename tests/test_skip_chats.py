"""Tests for skip-chats functionality."""

import pytest
from unittest.mock import Mock, patch

# We need to mock env vars and TelegramClient before importing transcriber
# because the module-level TelegramClient() call requires valid API credentials.
import os
os.environ.setdefault('TELEGRAM_API_ID', '12345')
os.environ.setdefault('TELEGRAM_API_HASH', 'test_hash')
os.environ.setdefault('TELEGRAM_PHONE', '+1234567890')
os.environ.setdefault('GROQ_API_KEY', 'test_key')

# Mock TelegramClient before importing
with patch('transcriber.TelegramClient'):
    from transcriber import should_skip_chat, SKIP_CHATS


class TestShouldSkipChat:
    """Test the should_skip_chat function."""

    def _make_chat(self, chat_id=None, username=None, title=None, first_name=None):
        """Helper to create a mock chat object."""
        chat = Mock()
        if username is not None:
            chat.username = username
        else:
            chat.username = None
        if title is not None:
            chat.title = title
        elif hasattr(chat, 'title'):
            delattr(chat, 'title')
        if first_name is not None:
            chat.first_name = first_name
        return chat

    @patch('transcriber.SKIP_CHATS', [])
    def test_empty_skip_list_never_skips(self):
        """When SKIP_CHATS is empty, no chats should be skipped."""
        chat = self._make_chat(chat_id=12345, username='testuser')
        assert should_skip_chat(12345, chat) is False

    @patch('transcriber.SKIP_CHATS', ['12345'])
    def test_skip_by_numeric_chat_id(self):
        """Skip chat by numeric ID (string match)."""
        chat = self._make_chat(chat_id=12345, username='testuser')
        assert should_skip_chat(12345, chat) is True

    @patch('transcriber.SKIP_CHATS', ['-1001234567890'])
    def test_skip_by_negative_chat_id(self):
        """Skip supergroup/channel by negative numeric ID."""
        chat = self._make_chat(chat_id=-1001234567890, title='My Channel')
        assert should_skip_chat(-1001234567890, chat) is True

    @patch('transcriber.SKIP_CHATS', ['@my_channel'])
    def test_skip_by_username_with_at(self):
        """Skip chat by @username."""
        chat = self._make_chat(chat_id=-1001234567890, username='my_channel')
        assert should_skip_chat(-1001234567890, chat) is True

    @patch('transcriber.SKIP_CHATS', ['my_channel'])
    def test_skip_by_username_without_at(self):
        """Skip chat by username without @ prefix."""
        chat = self._make_chat(chat_id=-1001234567890, username='my_channel')
        assert should_skip_chat(-1001234567890, chat) is True

    @patch('transcriber.SKIP_CHATS', ['family chat'])
    def test_skip_by_chat_title(self):
        """Skip group chat by title (case-insensitive)."""
        chat = self._make_chat(chat_id=-100999, title='Family Chat')
        assert should_skip_chat(-100999, chat) is True

    @patch('transcriber.SKIP_CHATS', ['alice'])
    def test_skip_by_first_name_dm(self):
        """Skip DM chat by first name."""
        chat = self._make_chat(chat_id=67890, first_name='Alice', username='alice123')
        assert should_skip_chat(67890, chat) is True

    @patch('transcriber.SKIP_CHATS', ['99999', '@other_channel'])
    def test_no_skip_when_not_in_list(self):
        """Don't skip when chat is not in SKIP_CHATS."""
        chat = self._make_chat(chat_id=12345, username='testuser')
        assert should_skip_chat(12345, chat) is False

    @patch('transcriber.SKIP_CHATS', ['111', '@channel1', 'My Group'])
    def test_skip_multiple_entries(self):
        """Test with multiple skip entries."""
        # Match by ID
        chat1 = self._make_chat(chat_id=111, username='someone')
        assert should_skip_chat(111, chat1) is True
        # Match by username
        chat2 = self._make_chat(chat_id=222, username='channel1')
        assert should_skip_chat(222, chat2) is True
        # Match by title
        chat3 = self._make_chat(chat_id=333, title='My Group')
        assert should_skip_chat(333, chat3) is True
        # No match
        chat4 = self._make_chat(chat_id=444, username='other')
        assert should_skip_chat(444, chat4) is False

    @patch('transcriber.SKIP_CHATS', ['@My_Channel', 'FAMILY CHAT'])
    def test_case_insensitive_matching(self):
        """All matching is case-insensitive."""
        # Username match (case-insensitive)
        chat1 = self._make_chat(chat_id=111, username='my_channel')
        assert should_skip_chat(111, chat1) is True
        # Title match (case-insensitive)
        chat2 = self._make_chat(chat_id=222, title='Family Chat')
        assert should_skip_chat(222, chat2) is True

    @patch('transcriber.SKIP_CHATS', ['@my_channel'])
    def test_chat_with_none_username(self):
        """Handle chats that have no username (e.g., private groups)."""
        chat = self._make_chat(chat_id=99999)
        chat.username = None
        assert should_skip_chat(99999, chat) is False

    @patch('transcriber.SKIP_CHATS', ['bob'])
    def test_chat_with_no_title_dm(self):
        """Handle DM chats that have no title (just first_name)."""
        chat = self._make_chat(chat_id=67890, first_name='Bob')
        if hasattr(chat, 'title'):
            delattr(chat, 'title')
        assert should_skip_chat(67890, chat) is True