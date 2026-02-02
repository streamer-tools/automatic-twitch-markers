"""
Unit tests for SQLite state store.
"""

import tempfile
import unittest
from pathlib import Path

from twitch_marker_agent.core.state_store import StateStore


class TestStateStore(unittest.TestCase):
    """Tests for StateStore class."""

    def setUp(self) -> None:
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.store = StateStore(self.db_path)

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_creation(self) -> None:
        """Test that database file is created on init."""
        self.assertTrue(self.db_path.exists())

    def test_mark_processed_and_check(self) -> None:
        """Test marking a stream as processed and checking status."""
        stream_id = "test_stream_123"

        # Should not be processed initially
        self.assertFalse(self.store.is_processed(stream_id))

        # Mark as processed
        self.store.mark_processed(stream_id)

        # Should now be processed
        self.assertTrue(self.store.is_processed(stream_id))

    def test_mark_processed_with_video_id(self) -> None:
        """Test marking with both stream_id and video_id."""
        stream_id = "stream_456"
        video_id = "video_789"

        self.store.mark_processed(stream_id, video_id=video_id)

        # Should find by video_id (primary key when provided)
        self.assertTrue(self.store.is_processed(stream_id, video_id=video_id))

    def test_mark_processed_with_export_path(self) -> None:
        """Test storing export path with processed record."""
        stream_id = "stream_export"
        export_path = "/path/to/exported/file.csv"

        self.store.mark_processed(stream_id, export_path=export_path)
        self.assertTrue(self.store.is_processed(stream_id))

    def test_get_processed_count(self) -> None:
        """Test counting processed streams."""
        self.assertEqual(self.store.get_processed_count(), 0)

        self.store.mark_processed("stream_1")
        self.assertEqual(self.store.get_processed_count(), 1)

        self.store.mark_processed("stream_2")
        self.assertEqual(self.store.get_processed_count(), 2)

    def test_duplicate_marking(self) -> None:
        """Test that re-marking a stream updates rather than duplicates."""
        stream_id = "duplicate_stream"

        self.store.mark_processed(stream_id)
        self.store.mark_processed(stream_id)  # Should update, not insert

        self.assertEqual(self.store.get_processed_count(), 1)


class TestTokenStorage(unittest.TestCase):
    """Tests for token storage functionality."""

    def setUp(self) -> None:
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.store = StateStore(self.db_path)

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_store_and_get_token(self) -> None:
        """Test storing and retrieving a token."""
        key = "refresh_token"
        value = "test_token_value_12345"

        # Store token
        self.store.store_token(key, value)

        # Retrieve token
        retrieved = self.store.get_token(key)
        self.assertEqual(retrieved, value)

    def test_get_nonexistent_token(self) -> None:
        """Test that getting a nonexistent token returns None."""
        result = self.store.get_token("nonexistent_key")
        self.assertIsNone(result)

    def test_update_token(self) -> None:
        """Test that storing a token with same key updates it."""
        key = "access_token"

        self.store.store_token(key, "old_value")
        self.store.store_token(key, "new_value")

        retrieved = self.store.get_token(key)
        self.assertEqual(retrieved, "new_value")

    def test_delete_token(self) -> None:
        """Test deleting a stored token."""
        key = "temp_token"
        self.store.store_token(key, "temp_value")

        # Delete should return True
        result = self.store.delete_token(key)
        self.assertTrue(result)

        # Token should no longer exist
        self.assertIsNone(self.store.get_token(key))

    def test_delete_nonexistent_token(self) -> None:
        """Test deleting a nonexistent token returns False."""
        result = self.store.delete_token("not_there")
        self.assertFalse(result)

    def test_multiple_tokens(self) -> None:
        """Test storing and retrieving multiple tokens."""
        tokens = {
            "access_token": "access_123",
            "refresh_token": "refresh_456",
            "expires_at": "2024-01-01T00:00:00Z",
        }

        for key, value in tokens.items():
            self.store.store_token(key, value)

        for key, value in tokens.items():
            self.assertEqual(self.store.get_token(key), value)


class TestStateStorePersistence(unittest.TestCase):
    """Tests for database persistence across instances."""

    def setUp(self) -> None:
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "persist_test.db"

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_data_persists_across_instances(self) -> None:
        """Test that data survives closing and reopening store."""
        # First instance - write data
        store1 = StateStore(self.db_path)
        store1.mark_processed("persistent_stream")
        store1.store_token("persist_key", "persist_value")
        store1.close()

        # Second instance - read data
        store2 = StateStore(self.db_path)
        self.assertTrue(store2.is_processed("persistent_stream"))
        self.assertEqual(store2.get_token("persist_key"), "persist_value")
        store2.close()


if __name__ == "__main__":
    unittest.main()
