"""
backup_result.py — data transfer objects for backup and verification outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class BackupResult:
    """Outcome of a backup creation operation."""

    success: bool
    backup_id: str
    backup_path: Path | None
    size_bytes: int
    file_count: int
    created_at: datetime
    error: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of a backup verification operation."""

    valid: bool
    backup_id: str
    checksum_errors: list[str] | None = None
    missing_files: list[str] | None = None
    error: str | None = None


@dataclass(frozen=True)
class BackupInfo:
    """Summary information of a verified backup ZIP archive."""

    backup_id: str
    backup_path: Path
    size_bytes: int
    created_at: datetime
    schema_version: str
    trackora_version: str
    backup_type: str
    file_count: int
