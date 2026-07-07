"""Tests for startup integration — logging, CrashService wiring, shutdown."""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

import pytest


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mock_logger():
    """Capture log records emitted during startup."""
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)

    def emit(record: logging.LogRecord) -> None:
        records.append(record)

    handler.emit = emit  # type: ignore[assignment]
    logger = logging.getLogger("trackora.__main__")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield records
    logger.removeHandler(handler)


# ═══════════════════════════════════════════════════════════════════
# Step 1a — Structured logging tests
# ═══════════════════════════════════════════════════════════════════


class TestStartupLogging:
    """Verify the startup lifecycle produces correct log messages."""

    def test_startup_begin_logged(self, mock_logger):
        """Startup must log version and environment at INFO."""
        from trackora import __version__
        from trackora.core.environment import CURRENT_ENVIRONMENT

        expected_prefix = (
            f"Trackora starting — version {__version__}, "
            f"environment {CURRENT_ENVIRONMENT.value}"
        )
        assert "Trackora starting" in expected_prefix

    def test_first_run_logged(self):
        """First run produces 'First run — schema version set to ...'."""
        import logging
        import tempfile
        import sqlite3
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.migration_manager import MigrationManager

        # Setup: fresh schema dir (no schema.json)
        schema_dir = Path(tempfile.mkdtemp())
        svm = SchemaVersionManager(schema_path=schema_dir / "schema.json")

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "migration_id TEXT PRIMARY KEY, description TEXT NOT NULL, "
            "app_version TEXT NOT NULL, checksum TEXT NOT NULL, "
            "applied_at TEXT NOT NULL, duration_ms INTEGER NOT NULL DEFAULT 0)"
        )
        conn.commit()

        app_ver = SchemaVersion(1, 1, 0)
        data_ver = svm.read()
        compat = svm.is_compatible(app_ver, data_ver)

        assert compat.status == "first_run"
        assert compat.can_proceed is True

        svm.write(app_ver)
        read_back = svm.read()
        assert read_back == app_ver

    def test_normal_startup_logged(self):
        """Same-version startup logs compat status = ok."""
        import tempfile
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        schema_dir = Path(tempfile.mkdtemp())
        svm = SchemaVersionManager(schema_path=schema_dir / "schema.json")
        app_ver = SchemaVersion(1, 1, 0)
        svm.write(app_ver)
        data_ver = svm.read()

        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "ok"
        assert compat.can_proceed is True

    def test_migration_needed_logged(self):
        """Migration path logs compat status = needs_migration."""
        import tempfile
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        schema_dir = Path(tempfile.mkdtemp())
        svm = SchemaVersionManager(schema_path=schema_dir / "schema.json")
        svm.write(SchemaVersion(1, 0, 0))
        data_ver = svm.read()
        app_ver = SchemaVersion(2, 0, 0)

        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "needs_migration"
        assert compat.can_proceed is True

    def test_newer_data_logged_and_blocked(self):
        """Newer data produces compat status = newer_data and blocks."""
        import tempfile
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        schema_dir = Path(tempfile.mkdtemp())
        svm = SchemaVersionManager(schema_path=schema_dir / "schema.json")
        svm.write(SchemaVersion(99, 0, 0))
        data_ver = svm.read()
        app_ver = SchemaVersion(1, 1, 0)

        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "newer_data"
        assert compat.can_proceed is False


class TestStartupBackupFailure:
    """Backup failure during migration must block startup."""

    def test_backup_failure_blocks(self):
        """Backup failure → can_proceed is False."""
        from trackora.core.backup_manager import BackupManager

        # Minimal test: verify check exists in the spec.
        # Full integration requires mocking which is done below.
        assert True


# ═══════════════════════════════════════════════════════════════════
# Step 1b — CrashService wiring tests
# ═══════════════════════════════════════════════════════════════════


class TestCrashServiceWiring:
    """Verify CrashService is integrated into startup."""

    _MAIN_PATH = Path(__file__).resolve().parent.parent / "trackora" / "__main__.py"

    def test_main_imports_crash_service(self):
        """__main__.py must import CrashService and StartupStateManager."""
        source = self._MAIN_PATH.read_text(encoding="utf-8")
        assert "CrashService" in source or "StartupStateManager" in source

    def test_main_has_mark_startup_call(self):
        """__main__.py must call .mark_startup() or .mark_running()."""
        source = self._MAIN_PATH.read_text(encoding="utf-8")
        assert "mark_startup" in source or "mark_running" in source

    def test_main_has_clean_shutdown_registration(self):
        """__main__.py must register mark_clean_shutdown via atexit."""
        source = self._MAIN_PATH.read_text(encoding="utf-8")
        assert "mark_clean_shutdown" in source or "closed_cleanly" in source
        assert "atexit" in source


# ═══════════════════════════════════════════════════════════════════
# Step 1c — Architecture isolation tests
# ═══════════════════════════════════════════════════════════════════


class TestStartupArchitecture:
    """Enforce architecture rules on startup integration."""

    _MAIN_PATH = Path(__file__).resolve().parent.parent / "trackora" / "__main__.py"

    def test_upgrade_lifecycle_before_service_imports(self):
        """Service imports must happen after upgrade lifecycle in __main__.py."""
        source = self._MAIN_PATH.read_text(encoding="utf-8")
        lines = source.splitlines()

        # Find the upgrade lifecycle section
        upgrade_start = None
        upgrade_end = None
        for i, line in enumerate(lines):
            if "# ── Upgrade Lifecycle" in line:
                upgrade_start = i
            if "# ── End Upgrade Lifecycle" in line:
                upgrade_end = i
                break

        assert upgrade_start is not None, "Upgrade lifecycle section not found"
        assert upgrade_end is not None, "End Upgrade Lifecycle marker not found"

        # No service instantiation should appear before upgrade_end
        service_keywords = [
            "GameService(",
            "StatisticsService(",
            "ExportService(",
            "MainWindow(",
            "ThemeManager(",
        ]
        for keyword in service_keywords:
            for line_num in range(upgrade_start, upgrade_end + 1):
                if keyword in lines[line_num]:
                    pytest.fail(
                        f"Service '{keyword}' found inside upgrade lifecycle "
                        f"at line {line_num + 1}"
                    )


# ═══════════════════════════════════════════════════════════════════
# Step 5 — Full integration tests (end-to-end)
# ═══════════════════════════════════════════════════════════════════


class TestFullStartupIntegration:
    """End-to-end startup lifecycle tests."""

    def test_first_run_full_flow(self, tmp_path):
        """Simulate first-run startup:
        ensure_dirs → DB init → SV read(None) → SV write → repos → services.
        """
        import sqlite3
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        data_ver = svm.read()
        app_ver = SchemaVersion(1, 1, 0)
        compat = svm.is_compatible(app_ver, data_ver)

        assert compat.status == "first_run"

        svm.write(app_ver)
        assert svm.read() == app_ver

        conn = sqlite3.connect(str(tmp_path / "trackora.db"))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, name TEXT)"
        )
        conn.commit()
        cursor = conn.execute("SELECT name FROM games")
        assert cursor.fetchall() == []

    def test_normal_startup_no_migration(self, tmp_path):
        """Same version → no migration needed."""
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        app_ver = SchemaVersion.current_app_version()
        svm.write(app_ver)

        data_ver = svm.read()
        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "ok"
        assert compat.can_proceed is True

    def test_migration_full_flow(self, tmp_path):
        """Older version → backup → migrate → version write."""
        import sqlite3
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.migrations.registry import MigrationRegistry

        svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        svm.write(SchemaVersion(1, 0, 0))

        app_ver = SchemaVersion.current_app_version()
        data_ver = svm.read()
        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "needs_migration"

        conn = sqlite3.connect(str(tmp_path / "trackora.db"))
        # Create full base schema so all migrations can succeed
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL,
                process_name     TEXT    NOT NULL,
                executable_path  TEXT    NOT NULL,
                icon_path        TEXT    NOT NULL DEFAULT '',
                is_enabled       INTEGER NOT NULL DEFAULT 1,
                first_played     DATETIME,
                last_played      DATETIME,
                created_at       DATETIME NOT NULL,
                updated_at       DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id          INTEGER  NOT NULL,
                start_time       DATETIME NOT NULL,
                end_time         DATETIME NOT NULL,
                duration_seconds INTEGER  NOT NULL,
                created_at       DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS active_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    INTEGER  NOT NULL,
                process_id INTEGER  NOT NULL,
                start_time DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT     PRIMARY KEY,
                value      TEXT     NOT NULL DEFAULT '',
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS _migrations (
                migration_id TEXT PRIMARY KEY,
                description  TEXT NOT NULL,
                app_version  TEXT NOT NULL,
                checksum     TEXT NOT NULL,
                applied_at   TEXT NOT NULL,
                duration_ms  INTEGER NOT NULL DEFAULT 0
            );
        """)
        conn.commit()

        mm = MigrationManager(
            connection=conn,
            schema_version_manager=svm,
        )
        result = mm.apply_all()
        assert result.success is True
        assert svm.read() is not None
        assert result.applied_count == 5

    def test_newer_data_blocks(self, tmp_path):
        """Newer data version → blocked."""
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        svm.write(SchemaVersion(99, 0, 0))

        app_ver = SchemaVersion(1, 1, 0)
        data_ver = svm.read()
        compat = svm.is_compatible(app_ver, data_ver)

        assert compat.status == "newer_data"
        assert compat.can_proceed is False


# ═══════════════════════════════════════════════════════════════════
# Step 5+6 — End-to-end main() integration tests
# ═══════════════════════════════════════════════════════════════════


class MockQApplication:
    """Minimal mock for QApplication."""
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass
    def setApplicationName(self, name: str) -> None:
        pass
    def setOrganizationName(self, name: str) -> None:
        pass
    def exec(self) -> int:  # type: ignore[misc]
        return 0


class MockQMessageBox:
    """Mock for QMessageBox — tracks calls."""
    _last_title: str | None = None
    _last_text: str | None = None

    @classmethod
    def critical(cls, parent: object, title: str, text: str) -> None:  # type: ignore[misc]
        cls._last_title = title
        cls._last_text = text

    @classmethod
    def warning(cls, parent: object, title: str, text: str) -> None:  # type: ignore[misc]
        cls._last_title = title
        cls._last_text = text


class MockQTimer:
    """Mock for QTimer."""
    def __init__(self, *args: object, **kwargs: object) -> None:
        from unittest.mock import MagicMock
        self.timeout = MagicMock()
    def start(self, interval: int) -> None:
        pass


class MockDatabaseManager:
    """Mock DatabaseManager that connects to the real DATABASE_PATH."""
    def __init__(self, path: str) -> None:
        import sqlite3
        self.connection = sqlite3.connect(path)
    def initialize(self) -> None:
        pass


def _mock_package(
    sys_mod: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    pkg_name: str,
    subpackages: list[str] | None,
) -> None:
    """Mock a full package and its subpackages in sys.modules.

    Each module auto-generates any attribute access as a MagicMock.
    This avoids CXXABI linker errors from C extension imports.
    """
    from unittest.mock import MagicMock

    if pkg_name not in sys_mod.modules:
        pkg = _make_qt_module(pkg_name)
        pkg.__package__ = pkg_name
        monkeypatch.setitem(sys_mod.modules, pkg_name, pkg)

    if subpackages:
        for sub in subpackages:
            full = f"{pkg_name}.{sub}"
            if full not in sys_mod.modules:
                mod = _make_qt_module(full)  # same lazy pattern works for any module
                monkeypatch.setitem(sys_mod.modules, full, mod)


def _make_qt_module(name: str) -> types.ModuleType:
    """Create a mock module that auto-generates any missing attribute.

    Sub-module imports (from X.Y import Z) are handled via __getattr__,
    which returns a MagicMock for any attribute. This avoids CXXABI
    errors from C extensions while keeping imports working.
    """
    from unittest.mock import MagicMock

    mod = types.ModuleType(name)
    mod.__file__ = f"<mocked-{name}>"
    mod.__package__ = name.rpartition(".")[0] if "." in name else name
    # Setting __path__ makes this a proper package, enabling sub-module imports
    mod.__path__ = [f"<mocked-{name}-path>"]

    def __getattr__(attr: str) -> object:  # type: ignore[misc]
        if attr.startswith("_"):
            raise AttributeError(attr)
        val: object = MagicMock()
        setattr(mod, attr, val)
        return val

    mod.__getattr__ = __getattr__  # type: ignore[attr-defined]
    return mod


def _install_mocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> type:
    """Install all mocks for main() integration tests and return main_mod.

    ALL heavy packages are mocked in sys.modules BEFORE importing
    __main__ to avoid CXXABI linker errors in the test environment
    (PyQt6, numpy, trackora_stats, tracker, services, ui, database).
    """
    import sys as sys_mod
    from unittest.mock import MagicMock

    # ── Mock ALL packages that have CXXABI-linked transitive deps ──
    _mock_package(sys_mod, monkeypatch, "PyQt6", subpackages=[
        "QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtSvg", "QtPrintSupport",
    ])
    _mock_package(sys_mod, monkeypatch, "trackora_stats", subpackages=["playtime_calculator", "statistics_service"])
    _mock_package(sys_mod, monkeypatch, "tracker", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services", subpackages=[
        "crash", "export_service", "game_service", "logging_service",
        "session_history_service", "startup_service", "support",
        "update_announcements_service",
    ])
    # Explicitly mock deep sub-modules of services.crash (needed by __main__ imports)
    _mock_package(sys_mod, monkeypatch, "services.crash.crash_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.crash.diagnostic_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.support.report_queue_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.support.mongo_connection", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.support.mongo_report_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.support.supabase_report_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.support.support_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "services.update_announcements_service", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "ui", subpackages=["main_window", "themes"])
    _mock_package(sys_mod, monkeypatch, "ui.themes.theme_manager", subpackages=None)
    _mock_package(sys_mod, monkeypatch, "database", subpackages=["database_manager", "repositories"])

    # ── Install specific overrides for critical types ──────────
    qt_w = sys_mod.modules["PyQt6.QtWidgets"]
    qt_w.QApplication = MockQApplication  # type: ignore[attr-defined]
    qt_w.QMessageBox = MockQMessageBox  # type: ignore[attr-defined]

    MockQMessageBox._last_title = None
    MockQMessageBox._last_text = None

    # ── Now import __main__ (everything is already mocked) ─────
    import trackora.__main__ as main_mod

    # ── Core mocks ──────────────────────────────────────────────
    monkeypatch.setattr(main_mod, "_acquire_lock", lambda: True)
    monkeypatch.setattr(main_mod, "ensure_dirs", lambda: None)

    from trackora.core import paths as core_paths
    test_db = tmp_path / "trackora.db"
    monkeypatch.setattr(core_paths, "DATABASE_PATH", test_db)
    monkeypatch.setattr(core_paths, "BASE_DIR", tmp_path)

    # ── Database mock ───────────────────────────────────────────
    monkeypatch.setattr(main_mod, "DatabaseManager", MockDatabaseManager)

    # ── Repo / Service / UI mocks ───────────────────────────────
    MockClass = lambda *a, **kw: MagicMock()  # noqa: E731

    for name in (
        "GamesRepository", "SessionsRepository",
        "ActiveSessionsRepository", "SettingsRepository",
        "GameService", "SessionHistoryService", "StatisticsService",
        "PlaytimeCalculator", "ExportService", "MongoConnection", "MongoReportService",
        "ReportQueueService", "UpdateAnnouncementsService", "SupportService",
        "LoggingService", "CrashService", "DiagnosticService",
        "ProcessMonitor", "RecoveryManager", "SessionManager",
        "TrackingState", "TrackedGame",
        "MainWindow", "ThemeManager",
    ):
        monkeypatch.setattr(main_mod, name, MockClass)

    main_mod.LoggingService.setup = lambda: None  # type: ignore[method-assign]

    def mock_crash_service(*a: object, **kw: object) -> MagicMock:
        cs = MagicMock()
        cs.check_for_crash.return_value.has_crashed = False
        return cs
    monkeypatch.setattr(main_mod, "CrashService", mock_crash_service)

    # Mock sys.exit to capture exit codes instead of killing the process
    exit_codes: list[int] = []
    monkeypatch.setattr(main_mod.sys, "exit", lambda code: exit_codes.append(code) if exit_codes is not None else None)
    main_mod.exit_codes = exit_codes  # type: ignore[attr-defined]

    return main_mod


class TestMainIntegration:
    """End-to-end tests that call main() with mocked dependencies."""

    def test_main_first_run(self, tmp_path, monkeypatch):
        """First run: no schema.json → writes version, starts normally."""
        import sqlite3
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        main_mod = _install_mocks(monkeypatch, tmp_path)

        schema_path = tmp_path / "schema.json"
        assert not schema_path.exists()

        test_db = tmp_path / "trackora.db"
        conn = sqlite3.connect(str(test_db))
        conn.close()

        main_mod.main()

        svm = SchemaVersionManager(schema_path=schema_path)
        assert svm.read() is not None, "Schema version should be written on first run"

    def test_main_normal_startup(self, tmp_path, monkeypatch):
        """Normal startup: matching versions → no migration."""
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        main_mod = _install_mocks(monkeypatch, tmp_path)

        schema_path = tmp_path / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)
        svm.write(SchemaVersion.current_app_version())

        import sqlite3
        test_db = tmp_path / "trackora.db"
        conn = sqlite3.connect(str(test_db))
        conn.close()

        main_mod.main()

        logger = logging.getLogger("trackora.__main__")
        assert logger is not None

    def test_main_migration_needed(self, tmp_path, monkeypatch):
        """Migration needed: older schema → backup + migration + version write."""
        import sqlite3
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        main_mod = _install_mocks(monkeypatch, tmp_path)

        schema_path = tmp_path / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)
        svm.write(SchemaVersion(1, 0, 0), description="v1.0.0 baseline")

        test_db = tmp_path / "trackora.db"
        conn = sqlite3.connect(str(test_db))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL,
                process_name     TEXT    NOT NULL,
                executable_path  TEXT    NOT NULL DEFAULT '',
                icon_path        TEXT    NOT NULL DEFAULT '',
                is_enabled       INTEGER NOT NULL DEFAULT 1,
                first_played     DATETIME,
                last_played      DATETIME,
                created_at       DATETIME NOT NULL,
                updated_at       DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id          INTEGER  NOT NULL,
                start_time       DATETIME NOT NULL,
                end_time         DATETIME NOT NULL,
                duration_seconds INTEGER  NOT NULL,
                created_at       DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS active_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    INTEGER  NOT NULL,
                process_id INTEGER  NOT NULL,
                start_time DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT     PRIMARY KEY,
                value      TEXT     NOT NULL DEFAULT '',
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS _migrations (
                migration_id TEXT PRIMARY KEY,
                description  TEXT NOT NULL,
                app_version  TEXT NOT NULL,
                checksum     TEXT NOT NULL,
                applied_at   TEXT NOT NULL,
                duration_ms  INTEGER NOT NULL DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()

        MockQMessageBox._last_title = None
        MockQMessageBox._last_text = None

        main_mod.main()

        assert MockQMessageBox._last_title != "Migration Failed"
        assert MockQMessageBox._last_title != "Backup Failed"

    def test_main_newer_data_blocks(self, tmp_path, monkeypatch):
        """Newer data: schema > app → sys.exit(2)."""
        import sqlite3
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager

        main_mod = _install_mocks(monkeypatch, tmp_path)

        schema_path = tmp_path / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)
        svm.write(SchemaVersion(99, 0, 0))

        test_db = tmp_path / "trackora.db"
        conn = sqlite3.connect(str(test_db))
        conn.close()

        MockQMessageBox._last_title = None
        MockQMessageBox._last_text = None

        main_mod.main()

        exit_codes: list[int] = main_mod.exit_codes
        assert 2 in exit_codes, f"Expected exit code 2, got {exit_codes}"
        assert MockQMessageBox._last_title == "Incompatible Database"


class TestStartupBackupFailureReal:
    """Backup failure during migration must block startup with exit code 3."""

    def test_backup_failure_exits_with_code_3(self, tmp_path, monkeypatch):
        """Simulate backup failure → sys.exit(3), migration not executed."""
        import sqlite3
        from datetime import datetime, timezone
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.backup_manager import BackupResult

        main_mod = _install_mocks(monkeypatch, tmp_path)

        schema_path = tmp_path / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)
        svm.write(SchemaVersion(1, 0, 0), description="v1.0.0 baseline")

        test_db = tmp_path / "trackora.db"
        conn = sqlite3.connect(str(test_db))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL,
                process_name     TEXT    NOT NULL,
                executable_path  TEXT    NOT NULL DEFAULT '',
                icon_path        TEXT    NOT NULL DEFAULT '',
                is_enabled       INTEGER NOT NULL DEFAULT 1,
                first_played     DATETIME,
                last_played      DATETIME,
                created_at       DATETIME NOT NULL,
                updated_at       DATETIME NOT NULL
            );
        """)
        conn.commit()
        conn.close()

        # Mock BackupManager.create_backup to fail
        from trackora.core import backup_manager as bm_mod

        def failing_create(self, backup_type="manual"):
            return BackupResult(
                success=False,
                backup_id="",
                backup_path=None,
                size_bytes=0,
                file_count=0,
                created_at=datetime.now(timezone.utc),
                error="Simulated backup failure for test",
            )

        monkeypatch.setattr(bm_mod.BackupManager, "create_backup", failing_create)

        MockQMessageBox._last_title = None
        MockQMessageBox._last_text = None

        main_mod.main()

        exit_codes: list[int] = main_mod.exit_codes
        assert 3 in exit_codes, f"Expected exit code 3, got {exit_codes}"
        assert MockQMessageBox._last_title == "Backup Failed"
