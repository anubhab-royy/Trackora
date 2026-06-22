"""
Phase 13I — Performance Validation.

Benchmarks 8 measurement domains against NFR targets.
Manual timing wrappers (no pytest-benchmark dependency).
"""

from __future__ import annotations

import gc
import json
import os
import random
import shutil
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pytest

from database.database_manager import DatabaseManager

from database.models.game import Game
from database.repositories.active_sessions_repository import ActiveSessionsRepository
from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import SessionsRepository
from database.repositories.settings_repository import SettingsRepository
from trackora.core.migration_manager import MigrationManager
from trackora.core.schema_version_manager import SchemaVersionManager
from trackora.core.schema_version import SchemaVersion
from trackora_stats.statistics_service import StatisticsService
from services.session_history_service import SessionHistoryService, SessionHistoryQuery
from tracker.discovery.orchestrator import DiscoveryOrchestrator
from tracker.discovery.detectors.folder_detector import FolderDetector
from tracker.discovery.detectors.steam_detector import SteamDetector
from tracker.discovery.models import CandidateGame

# ---------------------------------------------------------------------------
# NFR targets
# ---------------------------------------------------------------------------

NFR_MIGRATION_PER_MIGRATION_MS = 2000
NFR_MIGRATION_ALL_MS = 10000
NFR_DASHBOARD_REFRESH_MS = 5000
NFR_HISTORY_DEBOUNCE_MS = 300
NFR_HISTORY_PAGE_SIZE = 50
NFR_CHARTS_DAYS_DEFAULT = 30
NFR_CHARTS_MONTHS_DEFAULT = 12
NFR_REPORT_SUBMISSION_MS = 15000

# Iterations per benchmark
BENCH_ITERATIONS = 5
BENCH_ITERATIONS_FAST = 3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeBackupResult:
    def __init__(self, success: bool = True, backup_id: str = "") -> None:
        self.success = success
        self.backup_id = backup_id
        self.backup_path = None
        self.size_bytes = 0
        self.file_count = 0
        self.created_at = datetime.now(UTC).replace(tzinfo=None)
        self.error = ""


class _FakeBackupManager:
    """Minimal fake for migration benchmarks (avoids real DATABASE_PATH)."""

    def __init__(self) -> None:
        self.backups_created: list[str] = []
        self._counter = 0

    def create_backup(self, backup_type: str = "manual") -> _FakeBackupResult:
        self.backups_created.append(backup_type)
        self._counter += 1
        return _FakeBackupResult(success=True, backup_id=f"bk_{self._counter:04d}")

    def restore_backup(self, backup_id: str) -> _FakeBackupResult:
        return _FakeBackupResult(success=True, backup_id=backup_id)


@dataclass
class BenchmarkResult:
    name: str
    values_ms: list[float] = field(default_factory=list)
    nfr_target_ms: float | None = None

    @property
    def min_ms(self) -> float:
        return min(self.values_ms) if self.values_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.values_ms) if self.values_ms else 0.0

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.values_ms) if self.values_ms else 0.0

    @property
    def stdev_ms(self) -> float:
        return statistics.stdev(self.values_ms) if len(self.values_ms) > 1 else 0.0

    @property
    def passed(self) -> bool | None:
        if self.nfr_target_ms is None:
            return None
        return self.avg_ms <= self.nfr_target_ms

    def summary(self) -> str:
        status = (
            "PASS"
            if self.passed is True
            else "FAIL"
            if self.passed is False
            else "BASELINE"
        )
        nfr = f"  NFR: ≤{self.nfr_target_ms}ms" if self.nfr_target_ms else "  NFR: none"
        return (
            f"[{status:>8}] {self.name}: "
            f"avg={self.avg_ms:>8.2f}ms  min={self.min_ms:>8.2f}ms  "
            f"max={self.max_ms:>8.2f}ms  σ={self.stdev_ms:>6.2f}ms{nfr}"
        )


_results: list[BenchmarkResult] = []


def _record(name: str, values_ms: list[float], nfr_ms: float | None = None) -> BenchmarkResult:
    r = BenchmarkResult(name=name, values_ms=values_ms, nfr_target_ms=nfr_ms)
    _results.append(r)
    print(f"\n  {r.summary()}")
    return r


def _measure(callable: Callable[[], Any], iterations: int = BENCH_ITERATIONS) -> list[float]:
    gc.collect()
    gc.disable()
    values: list[float] = []
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        callable()
        elapsed_ms = (time.perf_counter() - start) * 1000
        values.append(elapsed_ms)
    gc.enable()
    return values


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def perf_db() -> Generator[Any, None, None]:
    """Scoped database populated with realistic test data."""
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "tracker.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.commit()

    conn.executescript("""
        CREATE TABLE games (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL,
            process_name      TEXT    NOT NULL DEFAULT '',
            executable_path   TEXT    NOT NULL DEFAULT '',
            icon_path         TEXT    NOT NULL DEFAULT '',
            is_enabled        INTEGER NOT NULL DEFAULT 1,
            platform          TEXT    DEFAULT NULL,
            platform_id       TEXT    DEFAULT NULL,
            is_auto_discovered INTEGER DEFAULT 0,
            first_played      DATETIME,
            last_played       DATETIME,
            created_at        DATETIME NOT NULL,
            updated_at        DATETIME NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id          INTEGER  NOT NULL REFERENCES games(id),
            start_time       DATETIME NOT NULL,
            end_time         DATETIME NOT NULL,
            duration_seconds INTEGER  NOT NULL DEFAULT 0,
            created_at       DATETIME NOT NULL
        );

        CREATE TABLE IF NOT EXISTS active_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    INTEGER  NOT NULL REFERENCES games(id),
            process_id INTEGER  NOT NULL DEFAULT 0,
            start_time DATETIME NOT NULL,
            created_at DATETIME NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT     PRIMARY KEY,
            value      TEXT     NOT NULL DEFAULT '',
            updated_at DATETIME NOT NULL
        );
    """)
    conn.commit()

    games_repo = GamesRepository(conn)
    sessions_repo = SessionsRepository(conn)

    # Insert 50 games
    for i in range(50):
        games_repo.add(Game(
            name=f"Game_{i:03d}",
            process_name=f"game_{i:03d}",
            executable_path=f"/usr/games/game_{i:03d}",
        ))

    # Insert 5,000 sessions over the last 90 days
    random.seed(42)
    games = games_repo.get_all()
    today = date.today()
    for day_offset in range(90):
        d = today - timedelta(days=day_offset)
        sessions_per_day = random.randint(3, 15)
        for _ in range(sessions_per_day):
            game = random.choice(games)
            start_ts = d.strftime("%Y-%m-%d") + f" {random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00"
            dur = random.randint(300, 7200)
            conn.execute(
                "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (game.id, start_ts, start_ts, dur, start_ts),
            )
    conn.commit()

    yield conn

    conn.close()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="function")
def perf_conn(perf_db: sqlite3.Connection) -> Generator[Any, None, None]:
    yield perf_db


@pytest.fixture(scope="function")
def perf_repos(perf_conn: Any) -> tuple[GamesRepository, SessionsRepository, ActiveSessionsRepository, SettingsRepository]:
    return (
        GamesRepository(perf_conn),
        SessionsRepository(perf_conn),
        ActiveSessionsRepository(perf_conn),
        SettingsRepository(perf_conn),
    )


@pytest.fixture(scope="function")
def perf_stats_service(perf_repos: tuple) -> StatisticsService:
    games_repo, sessions_repo, *_ = perf_repos
    return StatisticsService(sessions_repo, games_repo)


@pytest.fixture(scope="function")
def perf_history_service(perf_repos: tuple) -> SessionHistoryService:
    games_repo, sessions_repo, *_ = perf_repos
    return SessionHistoryService(sessions_repo, games_repo)


# ---------------------------------------------------------------------------
# Benchmark 1: Startup time
# ---------------------------------------------------------------------------


class TestStartupTime:
    """Measure DB init + schema read + migration + repo creation."""

    def test_db_initialization(self) -> None:
        """Benchmark: bare DatabaseManager init on a cold DB."""
        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                db = DatabaseManager(str(Path(tmp) / "t.db"))
                db.initialize()
                db.connection.close()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("startup.db_init", vals)

    def test_schema_read(self, perf_db: DatabaseManager) -> None:
        """Benchmark: SchemaVersionManager.read()."""

        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                svm = SchemaVersionManager(schema_path=Path(tmp) / "schema.json")
                svm.write(SchemaVersion.from_string("2.0.0"))
                svm.read()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("startup.schema_read", vals)

    def test_full_migration_lifecycle(self) -> None:
        """Benchmark: full migration lifecycle on a clean v1_0_0 DB."""

        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                db = DatabaseManager(str(Path(tmp) / "t.db"))
                db.initialize()
                conn = db.connection
                app_version = SchemaVersion.from_string("1.0.0")
                svm = SchemaVersionManager(schema_path=Path(tmp) / "schema.json")
                svm.write(app_version)
                bm = _FakeBackupManager()
                mm = MigrationManager(conn, svm, bm)
                mm.apply_all()
                conn.close()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("startup.full_migration_lifecycle", vals)

    def test_repo_creation(self, perf_conn: Any) -> None:
        """Benchmark: instantiate all 4 repositories."""

        def _run() -> None:
            GamesRepository(perf_conn)
            SessionsRepository(perf_conn)
            ActiveSessionsRepository(perf_conn)
            SettingsRepository(perf_conn)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("startup.repo_creation", vals)


# ---------------------------------------------------------------------------
# Benchmark 2: Dashboard load (5 aggregate queries)
# ---------------------------------------------------------------------------


class TestDashboardLoad:
    """Measure the 5 statistics queries composing a dashboard refresh."""

    def test_lifetime_stats(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(perf_stats_service.get_lifetime_stats, BENCH_ITERATIONS)
        _record("dashboard.lifetime_stats", vals, NFR_DASHBOARD_REFRESH_MS)

    def test_daily_stats(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(perf_stats_service.get_daily_stats, BENCH_ITERATIONS)
        _record("dashboard.daily_stats", vals, NFR_DASHBOARD_REFRESH_MS)

    def test_weekly_stats(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(perf_stats_service.get_weekly_stats, BENCH_ITERATIONS)
        _record("dashboard.weekly_stats", vals, NFR_DASHBOARD_REFRESH_MS)

    def test_monthly_stats(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(perf_stats_service.get_monthly_stats, BENCH_ITERATIONS)
        _record("dashboard.monthly_stats", vals, NFR_DASHBOARD_REFRESH_MS)

    def test_most_played_game(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(perf_stats_service.get_most_played_game, BENCH_ITERATIONS)
        _record("dashboard.most_played_game", vals, NFR_DASHBOARD_REFRESH_MS)

    def test_composite_dashboard_load(self, perf_stats_service: StatisticsService) -> None:
        """Simulate the actual DashboardController.load_dashboard_data sequence."""

        def _full_load() -> None:
            perf_stats_service.get_lifetime_stats()
            perf_stats_service.get_daily_stats()
            perf_stats_service.get_weekly_stats()
            perf_stats_service.get_monthly_stats()
            perf_stats_service.get_most_played_game()

        vals = _measure(_full_load, BENCH_ITERATIONS)
        _record("dashboard.composite_load", vals, NFR_DASHBOARD_REFRESH_MS)


# ---------------------------------------------------------------------------
# Benchmark 3: History load (paginated queries)
# ---------------------------------------------------------------------------


class TestHistoryLoad:
    """Measure paginated history queries with various filters."""

    def test_history_page_default(self, perf_history_service: SessionHistoryService) -> None:
        def _run() -> None:
            perf_history_service.query(SessionHistoryQuery(page=0, page_size=NFR_HISTORY_PAGE_SIZE))
        vals = _measure(_run, BENCH_ITERATIONS)
        _record("history.page_default", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_history_page_large(self, perf_history_service: SessionHistoryService) -> None:
        def _run() -> None:
            perf_history_service.query(SessionHistoryQuery(page=0, page_size=200))
        vals = _measure(_run, BENCH_ITERATIONS)
        _record("history.page_large", vals)

    def test_history_filtered_by_game(self, perf_history_service: SessionHistoryService) -> None:
        def _run() -> None:
            perf_history_service.query(SessionHistoryQuery(page=0, page_size=NFR_HISTORY_PAGE_SIZE, game_id=1))
        vals = _measure(_run, BENCH_ITERATIONS)
        _record("history.filtered_by_game", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_history_filtered_by_date_range(self, perf_history_service: SessionHistoryService) -> None:
        today = date.today()
        start = today - timedelta(days=7)

        def _run() -> None:
            perf_history_service.query(SessionHistoryQuery(
                page=0, page_size=NFR_HISTORY_PAGE_SIZE,
                date_from=start, date_to=today,
            ))
        vals = _measure(_run, BENCH_ITERATIONS)
        _record("history.filtered_by_date", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_history_filtered_by_duration(self, perf_history_service: SessionHistoryService) -> None:
        def _run() -> None:
            perf_history_service.query(SessionHistoryQuery(
                page=0, page_size=NFR_HISTORY_PAGE_SIZE,
                min_duration_minutes=30, max_duration_minutes=120,
            ))
        vals = _measure(_run, BENCH_ITERATIONS)
        _record("history.filtered_by_duration", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_history_complex_filter(self, perf_history_service: SessionHistoryService) -> None:
        """Full-text search + game + date range + duration + sort."""
        today = date.today()
        start = today - timedelta(days=30)

        def _run() -> None:
            perf_history_service.query(SessionHistoryQuery(
                page=0, page_size=NFR_HISTORY_PAGE_SIZE,
                search_text="Game_0",
                game_id=1,
                date_from=start, date_to=today,
                min_duration_minutes=10, max_duration_minutes=180,
                sort_by="duration", sort_order="desc",
            ))
        vals = _measure(_run, BENCH_ITERATIONS)
        _record("history.complex_filter", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_history_all_sessions_total(self, perf_history_service: SessionHistoryService) -> None:
        vals = _measure(perf_history_service.get_all_sessions_total_duration, BENCH_ITERATIONS)
        _record("history.total_duration", vals, NFR_HISTORY_DEBOUNCE_MS)


# ---------------------------------------------------------------------------
# Benchmark 4: Charts load
# ---------------------------------------------------------------------------


class TestChartsLoad:
    """Measure chart data aggregation queries."""

    def test_daily_activity_30(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(lambda: perf_stats_service.get_daily_activity(30), BENCH_ITERATIONS)
        _record("charts.daily_activity_30d", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_daily_activity_90(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(lambda: perf_stats_service.get_daily_activity(90), BENCH_ITERATIONS)
        _record("charts.daily_activity_90d", vals)

    def test_daily_activity_365(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(lambda: perf_stats_service.get_daily_activity(365), BENCH_ITERATIONS)
        _record("charts.daily_activity_365d", vals)

    def test_monthly_activity_12(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(lambda: perf_stats_service.get_monthly_activity(12), BENCH_ITERATIONS)
        _record("charts.monthly_activity_12m", vals, NFR_HISTORY_DEBOUNCE_MS)

    def test_monthly_activity_24(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(lambda: perf_stats_service.get_monthly_activity(24), BENCH_ITERATIONS)
        _record("charts.monthly_activity_24m", vals)

    def test_game_playtime_summaries(self, perf_stats_service: StatisticsService) -> None:
        vals = _measure(perf_stats_service.get_game_playtime_summaries, BENCH_ITERATIONS)
        _record("charts.game_playtime_summaries", vals, NFR_HISTORY_DEBOUNCE_MS)


# ---------------------------------------------------------------------------
# Benchmark 5: Discovery scan
# ---------------------------------------------------------------------------


class TestDiscoveryScan:
    """Measure the discovery orchestrator with various detector scenarios."""

    @pytest.fixture(scope="function")
    def perf_orchestrator_noop(self) -> DiscoveryOrchestrator:
        return DiscoveryOrchestrator()

    @pytest.fixture(scope="function")
    def perf_orchestrator_with_exclusions(self, perf_conn: Any) -> DiscoveryOrchestrator:
        games_repo = GamesRepository(perf_conn)

        def exists_by_path(p: str) -> bool:
            return False

        def exists_by_platform_id(platform: str, pid: str) -> bool:
            return False

        return DiscoveryOrchestrator(
            exists_by_executable_path=exists_by_path,
            exists_by_platform_id=exists_by_platform_id,
        )

    def test_orchestrator_instantiation(self) -> None:
        vals = _measure(lambda: DiscoveryOrchestrator(), BENCH_ITERATIONS_FAST)
        _record("discovery.orchestrator_creation", vals)

    def test_scan_empty(self, perf_orchestrator_noop: DiscoveryOrchestrator) -> None:
        """Scan with no detectors (cold start)."""
        vals = _measure(lambda: perf_orchestrator_noop.scan_all([]), BENCH_ITERATIONS_FAST)
        _record("discovery.scan_empty", vals)

    def test_scan_with_folder_detector(self) -> None:
        """Measure FolderDetector scanning a temp directory with files."""

        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                for i in range(10):
                    (Path(tmp) / f"game_{i:03d}.exe").touch()
                orch = DiscoveryOrchestrator()
                result = orch.scan_all([tmp])
                _ = result.candidates
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("discovery.scan_folder_detector", vals)

    def test_scan_steam_detector(self) -> None:
        """Measure SteamDetector (may produce no results on non-Steam systems)."""

        def _run() -> None:
            d = SteamDetector()
            _ = d.detect()

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("discovery.scan_steam_detector", vals)

    def test_folder_detector_isolated(self) -> None:
        """Measure FolderDetector directly with temp files."""

        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                for i in range(5):
                    (Path(tmp) / f"game_{i:03d}.exe").touch()
                d = FolderDetector(min_size_bytes=0)
                _ = d.detect([tmp])
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("discovery.folder_detector_isolated", vals)

    def test_deduplication(self) -> None:
        """Benchmark the deduplication logic with many candidates."""
        candidates = [
            CandidateGame(
                name=f"Game_{i:03d}",
                executable_path=f"/usr/games/game_{i:03d}.exe",
                platform="manual",
                platform_id="",
            )
            for i in range(200)
        ]

        orch = DiscoveryOrchestrator()

        def _run() -> None:
            # Access private method for isolated benchmark
            # pylint: disable=protected-access
            _ = DiscoveryOrchestrator._deduplicate(candidates)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("discovery.deduplication_200", vals)

    def test_exclude_existing(self, perf_conn: Any) -> None:
        """Benchmark exclude-existing with a real repository check."""
        games_repo = GamesRepository(perf_conn)

        def exists_by_path(p: str) -> bool:
            return games_repo.get_by_executable_path(p) is not None

        candidates = [
            CandidateGame(
                name=f"NewGame_{i:03d}",
                executable_path=f"/usr/games/new_game_{i:03d}.exe",
                platform="manual",
                platform_id="",
            )
            for i in range(100)
        ]

        orch = DiscoveryOrchestrator(
            exists_by_executable_path=exists_by_path,
        )

        def _run() -> None:
            # pylint: disable=protected-access
            _ = orch._exclude_existing(candidates)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("discovery.exclude_existing_100", vals)


# ---------------------------------------------------------------------------
# Benchmark 6: Migration time
# ---------------------------------------------------------------------------


class TestMigrationTime:
    """Measure migration execution end-to-end."""

    def test_migration_lifecycle_v1_to_v2(self) -> None:
        """Run pending migrations on a v1.0.0 DB and measure total time."""

        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                db = DatabaseManager(str(Path(tmp) / "t.db"))
                db.initialize()
                conn = db.connection
                app_ver = SchemaVersion.from_string("1.0.0")
                svm = SchemaVersionManager(schema_path=Path(tmp) / "schema.json")
                svm.write(app_ver)
                bm = _FakeBackupManager()
                mm = MigrationManager(conn, svm, bm)
                result = mm.apply_all()
                _ = result
                conn.close()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("migration.v1_to_v2_total", vals, NFR_MIGRATION_ALL_MS)

    def test_migration_empty_pending(self) -> None:
        """Run migrations when none are pending (fast path)."""

        def _run() -> None:
            tmp = tempfile.mkdtemp()
            try:
                app_ver = SchemaVersion(2, 0, 0)
                svm = SchemaVersionManager(schema_path=Path(tmp) / "schema.json")
                svm.write(app_ver)
                bm = _FakeBackupManager()
                db = DatabaseManager(str(Path(tmp) / "t.db"))
                db.initialize()
                conn = db.connection
                mm = MigrationManager(conn, svm, bm)
                result = mm.apply_all()
                _ = result
                conn.close()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("migration.none_pending", vals)
        # No pending migrations should be near-instant
        assert vals[-1] < 500, "Empty migration path took >500ms"

    def test_pre_migration_backup(self) -> None:
        """Measure BackupManager.create_backup call overhead (with FakeBackup)."""
        bm = _FakeBackupManager()

        def _run() -> None:
            _ = bm.create_backup("pre_migration")

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("migration.create_backup_overhead", vals)

    def test_migration_idempotent_apply(self) -> None:
        """Run apply_all twice — second run should be fast (no-op)."""
        tmp = tempfile.mkdtemp()
        try:
            app_ver = SchemaVersion.from_string("1.0.0")
            svm = SchemaVersionManager(schema_path=Path(tmp) / "schema.json")
            svm.write(app_ver)
            bm = _FakeBackupManager()
            db = DatabaseManager(str(Path(tmp) / "t.db"))
            db.initialize()
            conn = db.connection
            mm = MigrationManager(conn, svm, bm)
            mm.apply_all()

            def _run_again() -> None:
                mm2 = MigrationManager(conn, svm, bm)
                _ = mm2.apply_all()

            vals = _measure(_run_again, BENCH_ITERATIONS_FAST)
            _record("migration.idempotent_apply", vals)
            assert vals[-1] < 500, "Idempotent migration took >500ms"
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Benchmark 7: Report submission
# ---------------------------------------------------------------------------


class TestReportSubmission:
    """Measure serialization and mock-submission paths."""

    def test_report_data_serialization(self) -> None:
        """Measure assembling a diagnostic report payload."""

        def _run() -> None:
            report = {
                "app_version": "2.0.0",
                "os": "linux",
                "total_sessions": 5000,
                "total_playtime_seconds": 12345678,
                "games_tracked": 50,
                "generated_at": "2026-06-21T12:00:00",
                "environment": {"python": "3.13", "qt": "6", "platform": "linux"},
                "recent_errors": ["err1", "err2", "err3"],
                "performance": {"avg_query_ms": 2.5, "p95_query_ms": 15.0},
            }
            import json
            _ = json.dumps(report, indent=2)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("report.serialization", vals)

    def test_report_with_session_data(self, perf_repos: tuple) -> None:
        """Measure assembling a report with actual session data."""
        games_repo, sessions_repo, _, _ = perf_repos

        def _run() -> None:
            sessions = sessions_repo.get_all()
            games = games_repo.get_all()
            report = {
                "total_sessions": len(sessions),
                "total_playtime": sum(s.duration_seconds or 0 for s in sessions),
                "games": len(games),
                "session_sample": [
                    {"id": s.id, "game_id": s.game_id, "duration": s.duration_seconds}
                    for s in sessions[:100]
                ],
            }
            import json
            _ = json.dumps(report, indent=2)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("report.with_session_data", vals, NFR_REPORT_SUBMISSION_MS)

    def test_offline_queue_serialization(self) -> None:
        """Measure serializing the offline report queue."""

        def _run() -> None:
            queue = [
                {
                    "id": i,
                    "type": "crash_report",
                    "payload": {
                        "error": f"Test error {i}",
                        "traceback": f"line {i * 10}: exception",
                        "timestamp": "2026-06-21T12:00:00",
                    },
                    "created_at": "2026-06-21T12:00:00",
                    "retries": 0,
                }
                for i in range(50)
            ]
            import json
            _ = json.dumps(queue, indent=2)

        vals = _measure(_run, BENCH_ITERATIONS_FAST)
        _record("report.offline_queue_50", vals)


# ---------------------------------------------------------------------------
# Benchmark 8: Memory usage
# ---------------------------------------------------------------------------


class TestMemoryUsage:
    """Measure memory delta for key operations using tracemalloc."""

    KB = 1024
    MB = 1024 * 1024

    def _measure_mem_delta(
        self, callable: Callable[[], Any], *, peak: bool = False
    ) -> int:
        tracemalloc.start()
        gc.collect()
        before = tracemalloc.get_traced_memory()
        callable()
        gc.collect()
        after = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return (after[0 if not peak else 1] - before[0 if not peak else 1])

    def test_memory_dashboard_load(self, perf_stats_service: StatisticsService) -> None:
        delta = self._measure_mem_delta(
            lambda: (
                perf_stats_service.get_lifetime_stats(),
                perf_stats_service.get_daily_stats(),
                perf_stats_service.get_weekly_stats(),
                perf_stats_service.get_monthly_stats(),
                perf_stats_service.get_most_played_game(),
            )
        )
        _record("memory.dashboard_load", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_history_page(self, perf_history_service: SessionHistoryService) -> None:
        delta = self._measure_mem_delta(
            lambda: perf_history_service.query(
                SessionHistoryQuery(page=0, page_size=NFR_HISTORY_PAGE_SIZE)
            )
        )
        _record("memory.history_page", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_history_large_page(self, perf_history_service: SessionHistoryService) -> None:
        delta = self._measure_mem_delta(
            lambda: perf_history_service.query(
                SessionHistoryQuery(page=0, page_size=500)
            )
        )
        _record("memory.history_large_page", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_charts_30d(self, perf_stats_service: StatisticsService) -> None:
        delta = self._measure_mem_delta(
            lambda: perf_stats_service.get_daily_activity(30)
        )
        _record("memory.charts_30d", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_charts_12m(self, perf_stats_service: StatisticsService) -> None:
        delta = self._measure_mem_delta(
            lambda: perf_stats_service.get_monthly_activity(12)
        )
        _record("memory.charts_12m", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_all_sessions_load(self, perf_repos: tuple) -> None:
        _, sessions_repo, _, _ = perf_repos
        delta = self._measure_mem_delta(lambda: sessions_repo.get_all())
        _record("memory.all_sessions", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_game_playtime_summaries(self, perf_stats_service: StatisticsService) -> None:
        delta = self._measure_mem_delta(
            perf_stats_service.get_game_playtime_summaries
        )
        _record("memory.game_summaries", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")

    def test_memory_report_serialization(self) -> None:
        def _run() -> None:
            report = {
                "sessions": [{"id": i, "game_id": i % 50, "duration": 3600} for i in range(5000)],
                "games": [{"id": i, "name": f"Game_{i:03d}"} for i in range(50)],
            }
            import json
            _ = json.dumps(report, indent=2)

        delta = self._measure_mem_delta(_run)
        _record("memory.report_serialization", [delta / self.KB])
        print(f"\n    Memory delta: {delta / self.KB:.1f} KB")


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------


def test_print_performance_summary() -> None:
    """Print the full benchmark report."""
    print("\n" + "=" * 90)
    print("  PHASE 13I — PERFORMANCE VALIDATION SUMMARY")
    print("=" * 90)
    headers = ("DOMAIN", "STATUS", "AVG (ms)", "MIN (ms)", "MAX (ms)", "σ (ms)", "NFR (ms)")
    print(f"  {headers[0]:<30s} {headers[1]:>8s} {headers[2]:>10s} "
          f"{headers[3]:>10s} {headers[4]:>10s} {headers[5]:>10s} {headers[6]:>10s}")
    print("  " + "-" * 90)

    passes = 0
    fails = 0
    baselines = 0
    for r in _results:
        status = "PASS" if r.passed is True else "FAIL" if r.passed is False else "N/A"
        print(f"  {r.name:<30s} {status:>8s} {r.avg_ms:>10.2f} {r.min_ms:>10.2f} "
              f"{r.max_ms:>10.2f} {r.stdev_ms:>10.2f} "
              f"{f'≤{r.nfr_target_ms}' if r.nfr_target_ms else '—':>10s}")
        if r.passed is True:
            passes += 1
        elif r.passed is False:
            fails += 1
        else:
            baselines += 1

    print("  " + "-" * 90)
    print(f"  Total: {len(_results)} benchmarks | PASS: {passes} | "
          f"FAIL: {fails} | BASELINE: {baselines}")
    print("=" * 90)

    assert fails == 0, f"{fails} benchmark(s) exceeded NFR targets"
