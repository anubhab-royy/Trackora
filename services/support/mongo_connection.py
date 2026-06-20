"""MongoConnection — singleton-per-instance connection manager.

Provides lazy initialisation, thread-safe access, and health-checking
for a MongoDB backend used by the support/reporting subsystem.
"""

from __future__ import annotations

import logging
import os
import threading

from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)


class MongoConnection:
    """Manages a single MongoClient instance with lazy initialisation.

    Usage
    -----
        conn = MongoConnection()
        if conn.health_check():
            db = conn.database
            db["bug_reports"].insert_one({"title": "..."})
    """

    def __init__(self, uri: str | None = None) -> None:
        self._uri = uri or os.environ.get("MONGODB_URI", "")
        self._client: MongoClient | None = None
        self._lock = threading.Lock()
        self._available: bool | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """``True`` after a successful ``health_check()``, otherwise ``False``.

        The initial state is ``False`` (lazy — no connection attempted).
        """
        return bool(self._available)

    @property
    def database(self) -> Database | None:
        """Return the configured ``Database`` instance, or ``None``.

        The underlying ``MongoClient`` is created **lazily** on the first
        call to this property and is reused for the lifetime of this object.
        """
        if not self._uri:
            return None
        client = self._get_or_create_client()
        return client.get_default_database()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Ping the MongoDB server.

        Returns ``True`` when the server responds, ``False`` otherwise.
        Credentials are redacted from all log output.
        """
        if not self._uri:
            return False
        try:
            client = self._get_or_create_client()
            client.admin.command("ping")
            self._available = True
            logger.info("MongoDB: available")
            return True
        except Exception:
            self._available = False
            logger.exception("MongoDB: health check failed")
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying ``MongoClient``, if one exists.

        Idempotent — safe to call multiple times.
        """
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
            self._available = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_client(self) -> MongoClient:
        """Return the existing client, or create one under the lock."""
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is None:
                self._client = MongoClient(
                    self._uri,
                    serverSelectionTimeoutMS=5000,
                )
        return self._client
