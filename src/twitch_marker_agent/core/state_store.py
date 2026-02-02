"""
SQLite-based state store for Twitch Marker Agent.

Provides persistent storage for:
- Processed VOD/stream IDs (to prevent duplicate exports)
- OAuth tokens (refresh token storage)

The StateStore is designed with a swappable abstraction layer
so it can later be replaced with Windows Credential Manager or
other secure storage backends.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Any


class StateStore:
    """
    SQLite-backed persistent state storage.

    Handles:
    - Tracking processed stream/VOD IDs
    - Storing and retrieving OAuth tokens

    Thread-safety: This class is NOT thread-safe. Create separate
    instances for each thread, or implement external locking.
    """

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize the state store.

        Creates the database file and tables if they don't exist.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Table for processed VODs/streams
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_streams (
                    id TEXT PRIMARY KEY,
                    stream_id TEXT,
                    video_id TEXT,
                    processed_at TEXT NOT NULL,
                    export_path TEXT
                )
            """)

            # Table for OAuth tokens
            # TODO: Consider encryption for token storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.commit()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a database connection context manager.

        Yields:
            SQLite connection object.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Processed Streams API
    # -------------------------------------------------------------------------

    def mark_processed(
        self,
        stream_id: str,
        video_id: str | None = None,
        export_path: str | None = None,
    ) -> None:
        """
        Mark a stream as processed to prevent duplicate exports.

        Args:
            stream_id: Twitch stream ID.
            video_id: Optional VOD ID if available.
            export_path: Optional path to exported file.
        """
        # Use stream_id as primary key, or video_id if stream_id not available
        record_id = video_id or stream_id
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO processed_streams
                (id, stream_id, video_id, processed_at, export_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record_id, stream_id, video_id, now, export_path),
            )
            conn.commit()

    def is_processed(self, stream_id: str, video_id: str | None = None) -> bool:
        """
        Check if a stream has already been processed.

        Args:
            stream_id: Twitch stream ID.
            video_id: Optional VOD ID to check.

        Returns:
            True if already processed, False otherwise.
        """
        record_id = video_id or stream_id

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_streams WHERE id = ?",
                (record_id,),
            )
            return cursor.fetchone() is not None

    def get_processed_count(self) -> int:
        """
        Get total count of processed streams.

        Returns:
            Number of processed streams.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM processed_streams")
            row = cursor.fetchone()
            return row[0] if row else 0

    # -------------------------------------------------------------------------
    # Token Storage API (Abstraction for future swap to Credential Manager)
    # -------------------------------------------------------------------------

    def store_token(self, key: str, value: str) -> None:
        """
        Store a token value.

        This abstraction allows future migration to Windows Credential
        Manager or other secure storage without changing calling code.

        Args:
            key: Token identifier (e.g., "refresh_token", "access_token").
            value: Token value to store.
        """
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO tokens (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, now),
            )
            conn.commit()

    def get_token(self, key: str) -> str | None:
        """
        Retrieve a stored token value.

        Args:
            key: Token identifier.

        Returns:
            Token value if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM tokens WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row["value"] if row else None

    def delete_token(self, key: str) -> bool:
        """
        Delete a stored token.

        Args:
            key: Token identifier.

        Returns:
            True if token was deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM tokens WHERE key = ?",
                (key,),
            )
            conn.commit()
            return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """
        Close the state store.

        Currently a no-op since connections are opened per-operation,
        but included for API completeness and future connection pooling.
        """
        # Connections are closed after each operation via context manager
        pass
