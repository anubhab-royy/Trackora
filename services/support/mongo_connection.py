"""MongoConnection — singleton-per-instance connection manager.

Provides lazy initialisation, thread-safe access, and health-checking
for a MongoDB backend used by the support/reporting subsystem.
"""

from __future__ import annotations

import logging
import os
import threading
from enum import Enum
from typing import Optional, Callable

from pymongo import MongoClient
from pymongo.database import Database
import pymongo.errors

logger = logging.getLogger(__name__)

SUBSYSTEM = "MongoDB"


class MongoValidationStatus(Enum):
    """Structured validation status categories for MongoDB connection checks."""
    CONNECTED = "Connected"
    CONFIGURATION_MISSING = "Configuration Missing"
    AUTHENTICATION_FAILED = "Authentication Failed"
    DATABASE_UNREACHABLE = "Database Unreachable"
    TIMEOUT = "Timeout"
    PERMISSION_ERROR = "Permission Error"
    NETWORK_ERROR = "Network Error"
    DNS_ERROR = "DNS Error"
    UNKNOWN_ERROR = "Unknown Error"


class MongoConnection:
    """Manages a single MongoClient instance with lazy initialisation.

    Usage
    -----
        conn = MongoConnection()
        if conn.health_check():
            db = conn.database
            db["bug_reports"].insert_one({"title": "..."})
    """

    def __init__(
        self,
        uri: str | None = None,
        database_name: str | None = None,
    ) -> None:
        self._uri = uri or os.environ.get("MONGODB_URI", "")
        self._database_name = database_name or os.environ.get("MONGODB_DATABASE", "")
        self._client: MongoClient | None = None
        self._lock = threading.Lock()
        self._available: bool | None = None

        # T-230: Caching attributes for validation diagnostics
        self._cached_status: MongoValidationStatus | None = None
        self._last_error: str | None = None
        self._auth_failed: bool = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """``True`` after a successful connection validation, otherwise ``False``."""
        if self._cached_status is not None:
            return self._cached_status == MongoValidationStatus.CONNECTED
        return bool(self._available)

    @property
    def last_error(self) -> str | None:
        """Returns the last recorded error message, or None."""
        return self._last_error

    @property
    def auth_failed(self) -> bool:
        """Returns True if the last validation failed due to authentication credentials."""
        return self._auth_failed

    @property
    def validation_status(self) -> MongoValidationStatus:
        """Returns the current validation status enum."""
        return self._cached_status or MongoValidationStatus.UNKNOWN_ERROR

    @property
    def is_pending(self) -> bool:
        """Returns True if initial validation is still in progress."""
        return self._cached_status is None

    @property
    def database(self) -> Database | None:
        """Return the configured ``Database`` instance, or ``None``.

        The underlying ``MongoClient`` is created **lazily** on the first
        call to this property and is reused for the lifetime of this object.
        """
        if not self._uri:
            return None
        client = self._get_or_create_client()
        try:
            db = client.get_default_database()
            if db is not None:
                return db
        except Exception as e:
            logger.error("[%s] get_default_database() failed (%s: %s)", SUBSYSTEM, e.__class__.__name__, e)
        if self._database_name:
            return client[self._database_name]
        return None

    # ------------------------------------------------------------------
    # Validation Pipeline (T-230)
    # ------------------------------------------------------------------

    def validate(self, force: bool = False) -> MongoValidationStatus:
        """Performs comprehensive validation checks on the MongoDB connection configuration & readiness.

        Results are cached to avoid redundant network overhead.
        """
        with self._lock:
            # If already connected, reuse cached state to avoid repeated network pings
            if self._cached_status == MongoValidationStatus.CONNECTED and not force:
                return self._cached_status

            # If other errors cached and not forcing, reuse cached state
            if self._cached_status is not None and not force:
                return self._cached_status

            logger.debug("[%s] Validation started", SUBSYSTEM)

            # 1. MongoDB URI presence check
            if not self._uri:
                self._cached_status = MongoValidationStatus.CONFIGURATION_MISSING
                self._last_error = "MONGODB_URI is empty or unset."
                self._auth_failed = False
                self._available = False
                logger.warning("[%s] Validation failed (ConfigurationMissing)", SUBSYSTEM)
                return self._cached_status

            # 2. URI Format Check
            uri_db = None
            try:
                from pymongo.uri_parser import parse_uri
                parsed = parse_uri(self._uri)
                uri_db = parsed.get("database")
            except Exception as exc:
                self._cached_status = MongoValidationStatus.CONFIGURATION_MISSING
                self._last_error = f"Invalid MONGODB_URI format: {exc}"
                self._auth_failed = False
                self._available = False
                logger.error("[%s] Validation failed (InvalidURI: %s)", SUBSYSTEM, exc)
                return self._cached_status

            # 3. Database name check
            db_name = self._database_name or uri_db
            if not db_name:
                self._cached_status = MongoValidationStatus.CONFIGURATION_MISSING
                self._last_error = "Database name is not configured."
                self._auth_failed = False
                self._available = False
                logger.warning("[%s] Validation failed (ConfigurationMissing: no database name)", SUBSYSTEM)
                return self._cached_status

            logger.debug("[%s] Configuration loaded", SUBSYSTEM)

            # 4. Connection & Ping reachability checks
            temp_client = None
            try:
                # Use short timeouts to detect offline failures rapidly without blocking
                temp_client = MongoClient(
                    self._uri,
                    serverSelectionTimeoutMS=3000,
                    connectTimeoutMS=3000,
                )
                logger.debug("[%s] Connection established", SUBSYSTEM)

                # Ping Cluster
                temp_client.admin.command("ping")
                logger.debug("[%s] Ping successful", SUBSYSTEM)

                # Verify Database Reachability & Collection CRUD (Read/Write Permissions)
                db = temp_client[db_name]
                required_cols = ["bug_reports", "feature_requests", "feedback", "crash_reports"]

                for col_name in required_cols:
                    # Read permission check
                    db[col_name].find_one({})

                    # Write permission check (Insert and immediately delete validation document)
                    test_doc = {"_validation_test": True}
                    res = db[col_name].insert_one(test_doc)
                    db[col_name].delete_one({"_id": res.inserted_id})

                self._cached_status = MongoValidationStatus.CONNECTED
                self._last_error = None
                self._auth_failed = False
                self._available = True

            except Exception as exc:
                self._cached_status = self._classify_exception(exc)
                self._last_error = str(exc)
                self._available = False

                if self._cached_status == MongoValidationStatus.AUTHENTICATION_FAILED:
                    self._auth_failed = True
                    logger.error("[%s] Validation failed (AuthenticationFailed)", SUBSYSTEM)
                else:
                    self._auth_failed = False
                    logger.warning("[%s] Validation failed (%s)", SUBSYSTEM, self._cached_status.value)

            finally:
                if temp_client is not None:
                    temp_client.close()

            if self._cached_status == MongoValidationStatus.CONNECTED:
                logger.info("[%s] Validation completed (Connected)", SUBSYSTEM)
            else:
                logger.warning("[%s] Validation completed (%s)", SUBSYSTEM, self._cached_status.value)
            return self._cached_status

    def validate_async(self, callback: Callable[[MongoValidationStatus], None] | None = None) -> None:
        """Runs the validation logic asynchronously in a background thread to prevent UI blocks."""
        def run_validation():
            status = self.validate(force=True)
            if callback:
                callback(status)

        thread = threading.Thread(target=run_validation, name="MongoValidationThread", daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self, force: bool = False) -> bool:
        """Check connection state, running validation checks to recover/reconnect if not healthy."""
        if self._cached_status == MongoValidationStatus.CONNECTED and not force:
            return True
        status = self.validate(force=force)
        return status == MongoValidationStatus.CONNECTED

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
            self._cached_status = None
            self._last_error = None
            self._auth_failed = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_client(self) -> MongoClient:
        """Return the existing client, or create one under the lock."""
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is None:
                try:
                    self._client = MongoClient(
                        self._uri,
                        serverSelectionTimeoutMS=5000,
                    )
                except Exception as e:
                    logger.error(
                        "[%s] Client creation failed (%s: %s)",
                        SUBSYSTEM, e.__class__.__name__, e,
                    )
                    raise
        return self._client

    def _classify_exception(self, exc: Exception) -> MongoValidationStatus:
        msg = str(exc).lower()

        if isinstance(exc, (pymongo.errors.ConfigurationError, ValueError)):
            return MongoValidationStatus.CONFIGURATION_MISSING

        # Check for network/DNS/Timeout details in message prior to general types
        if "dns" in msg or "resolve" in msg or "gai error" in msg or "temporary failure" in msg:
            return MongoValidationStatus.DNS_ERROR

        if "timeout" in msg or isinstance(exc, pymongo.errors.ServerSelectionTimeoutError):
            return MongoValidationStatus.TIMEOUT

        if isinstance(exc, pymongo.errors.OperationFailure):
            # Error code 18 corresponds to AuthenticationFailed in MongoDB
            if exc.code == 18 or "auth failed" in msg or "authentication failed" in msg:
                return MongoValidationStatus.AUTHENTICATION_FAILED
            # Error code 13 corresponds to Unauthorized in MongoDB
            if exc.code == 13 or "not authorized" in msg or "unauthorized" in msg:
                return MongoValidationStatus.PERMISSION_ERROR
            return MongoValidationStatus.DATABASE_UNREACHABLE

        if isinstance(exc, pymongo.errors.ConnectionFailure):
            return MongoValidationStatus.NETWORK_ERROR

        return MongoValidationStatus.UNKNOWN_ERROR
