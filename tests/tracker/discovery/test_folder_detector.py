"""Tests for FolderDetector."""

from __future__ import annotations

from pathlib import Path

from tracker.discovery.detectors.folder_detector import FolderDetector


class TestFolderDetector:
    """FolderDetector tests."""

    def test_scan_finds_executables(self, tmp_path: Path) -> None:
        """Scan directory and return candidates for .exe files."""
        game1 = tmp_path / "game1.exe"
        game1.write_text("x" * 2_000_000)
        game2 = tmp_path / "game2.exe"
        game2.write_text("y" * 2_000_000)

        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect([str(tmp_path)])

        assert len(results) == 2
        names = {r.name for r in results}
        assert "Game1" in names  # title-cased from stem
        assert "Game2" in names
        for r in results:
            assert r.platform == "generic"
            assert r.platform_id

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Return empty list when directory has no executables."""
        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect([str(tmp_path)])
        assert results == []

    def test_minimum_file_size_filter(self, tmp_path: Path) -> None:
        """Exclude files smaller than minimum size."""
        small = tmp_path / "small.exe"
        small.write_text("tiny")  # 4 bytes, below 1 MB default

        detector = FolderDetector(min_size_bytes=1_048_576)
        results = detector.detect([str(tmp_path)])
        assert results == []

    def test_overrides_min_size(self, tmp_path: Path) -> None:
        """Allow overriding minimum file size for testing."""
        small = tmp_path / "small.exe"
        small.write_text("tiny")

        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect([str(tmp_path)])
        assert len(results) == 1

    def test_no_folders_configured(self) -> None:
        """Return empty list when no folders are configured."""
        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect()
        assert results == []

    def test_nonexistent_folder(self) -> None:
        """Skip nonexistent folders without error."""
        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect(["/nonexistent/path"])
        assert results == []

    def test_excludes_hidden_directories(self, tmp_path: Path) -> None:
        """Skip files in hidden directories."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        exe = hidden / "game.exe"
        exe.write_text("x" * 2_000_000)

        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect([str(tmp_path)])
        assert results == []

    def test_excludes_system_dirs(self, tmp_path: Path) -> None:
        """System directories are excluded from results."""
        exe = tmp_path / "game.exe"
        exe.write_text("x" * 2_000_000)
        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect(["/nonexistent/bin", "/nonexistent/usr/bin", str(tmp_path)])
        assert len(results) == 1

    def test_deduplicates_by_path(self, tmp_path: Path) -> None:
        """Same path scanned twice produces one result."""
        exe = tmp_path / "game.exe"
        exe.write_text("x" * 2_000_000)

        detector = FolderDetector(min_size_bytes=1)
        results = detector.detect([str(tmp_path), str(tmp_path)])
        assert len(results) == 1

    def test_depth_limit(self, tmp_path: Path) -> None:
        """Respect max_depth parameter and stop at that depth."""
        # depth=2: tmp/a/b/deep.exe  (should NOT be found at max_depth=1)
        deep_dir = tmp_path / "a" / "b"
        deep_dir.mkdir(parents=True)
        (deep_dir / "deep.exe").write_text("x" * 2_000_000)

        # depth=1: tmp/c/shallow.exe  (SHOULD be found at max_depth=1)
        shallow_dir = tmp_path / "c"
        shallow_dir.mkdir()
        shallow_exe = shallow_dir / "shallow.exe"
        shallow_exe.write_text("x" * 2_000_000)

        # max_depth=1: only files in root and direct subdirectories
        detector = FolderDetector(min_size_bytes=1, max_depth=1)
        results = detector.detect([str(tmp_path)])
        assert len(results) == 1
        assert results[0].name == "Shallow"
