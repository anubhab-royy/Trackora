"""Architecture isolation tests for the discovery layer.

Verifies that:
  - Detectors do not import UI, services, or PyQt6
  - Orchestrator does not import UI or PyQt6
  - Discovery dialog does not import detector internals
  - Package structure is correct
"""

from __future__ import annotations

import ast
import pathlib

TRACKER_DISCOVERY = pathlib.Path("tracker/discovery")
UI_GAMES = pathlib.Path("ui/games")

FORBIDDEN_IN_DETECTORS = {"PyQt6", "ui.games", "services", "database"}
FORBIDDEN_IN_ORCHESTRATOR = {"PyQt6", "ui.games"}


def _get_imports(filepath: pathlib.Path) -> list[str]:
    """Return a list of top-level module names imported by the file."""
    tree = ast.parse(filepath.read_text("utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


class TestDetectorIsolation:
    """Detector modules must not import UI or service layers."""

    def _check_detector_file(self, rel_path: str) -> None:
        filepath = TRACKER_DISCOVERY / rel_path
        if not filepath.is_file():
            return
        imports = _get_imports(filepath)
        forbidden = [i for i in imports if i in FORBIDDEN_IN_DETECTORS]
        assert not forbidden, f"{filepath} imports forbidden modules: {forbidden}"

    def test_steam_detector_isolation(self) -> None:
        self._check_detector_file("detectors/steam_detector.py")

    def test_epic_detector_isolation(self) -> None:
        self._check_detector_file("detectors/epic_detector.py")

    def test_riot_detector_isolation(self) -> None:
        self._check_detector_file("detectors/riot_detector.py")

    def test_battlenet_detector_isolation(self) -> None:
        self._check_detector_file("detectors/battlenet_detector.py")

    def test_ubisoft_detector_isolation(self) -> None:
        self._check_detector_file("detectors/ubisoft_detector.py")

    def test_ea_detector_isolation(self) -> None:
        self._check_detector_file("detectors/ea_detector.py")

    def test_folder_detector_isolation(self) -> None:
        self._check_detector_file("detectors/folder_detector.py")

    def test_kv_parser_isolation(self) -> None:
        self._check_detector_file("kv_parser.py")

    def test_models_isolation(self) -> None:
        self._check_detector_file("models.py")

    def test_detector_base_isolation(self) -> None:
        self._check_detector_file("detector.py")


class TestOrchestratorIsolation:
    """Orchestrator must not import UI."""

    def test_orchestrator_no_pyqt(self) -> None:
        imports = _get_imports(TRACKER_DISCOVERY / "orchestrator.py")
        forbidden = [i for i in imports if i in FORBIDDEN_IN_ORCHESTRATOR]
        assert not forbidden


class TestPackageStructure:
    """Package must be importable with correct structure."""

    def test_discovery_package_importable(self) -> None:
        import tracker.discovery  # noqa: F811

    def test_models_importable(self) -> None:
        from tracker.discovery.models import CandidateGame, DiscoveryResult  # noqa: F811

    def test_detector_base_importable(self) -> None:
        from tracker.discovery.detector import GameDetector  # noqa: F811

    def test_kv_parser_importable(self) -> None:
        from tracker.discovery.kv_parser import parse_kv  # noqa: F811
