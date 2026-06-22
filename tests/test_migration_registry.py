"""Tests for MigrationRegistry — discovery, sorting, lookup."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest


def _migration_module(
    migration_id: str,
    description: str,
    app_version: str,
) -> str:
    """Generate source code for a minimal valid Migration subclass."""
    return f'''
from __future__ import annotations
from trackora.core.migration_manager import Migration


class _AutoMig(Migration):
    migration_id = {migration_id!r}
    description = {description!r}
    app_version = {app_version!r}

    def upgrade(self, connection: object) -> None:
        pass

    def downgrade(self, connection: object) -> None:
        pass
'''


def _create_temp_package(
    tmp_path: Path,
    modules: dict[str, str],
) -> tuple[str, Path]:
    """Create a temporary Python package with given modules.

    Returns (package_name, package_dir).
    """
    pkg_name = f"_test_mig_{uuid.uuid4().hex[:8]}"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text(
        "# test migration package\n",
        encoding="utf-8",
    )

    for mod_name, source in modules.items():
        (pkg_dir / f"{mod_name}.py").write_text(source, encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    return pkg_name, pkg_dir


@pytest.fixture(autouse=True)
def _clean_sys_path(request: pytest.FixtureRequest) -> None:
    """Remove any _test_mig_* entries from sys.path after each test."""
    yield
    for item in list(sys.path):
        if "_test_mig_" in item:
            sys.path.remove(item)


class TestDiscoverEmptyPackage:
    """No migrations found in an empty migration package."""

    def test_discover_empty_package_returns_empty_list(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        pkg_name, _ = _create_temp_package(tmp_path, {})
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            assert result == []
        finally:
            sys.path.remove(str(tmp_path))

    def test_discover_package_with_only_init_returns_empty(
        self, tmp_path: Path
    ) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        pkg_name, _ = _create_temp_package(tmp_path, {})
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            assert result == []
        finally:
            sys.path.remove(str(tmp_path))


class TestDiscoverWithMigrations:
    """Discovery finds and returns concrete Migration subclasses."""

    def test_discover_returns_one_migration(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        code = _migration_module("v2_0_0_test", "Test migration", "2.0.0")
        pkg_name, _ = _create_temp_package(tmp_path, {"v2_0_0_test": code})
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            assert len(result) == 1
            assert result[0].migration_id == "v2_0_0_test"
        finally:
            sys.path.remove(str(tmp_path))

    def test_discover_returns_sorted_by_migration_id(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        modules = {
            "v2_0_0_z": _migration_module("v2_0_0_z", "Z migration", "2.0.0"),
            "v1_0_0_a": _migration_module("v1_0_0_a", "A migration", "1.0.0"),
            "v2_0_0_m": _migration_module("v2_0_0_m", "M migration", "2.0.0"),
        }
        pkg_name, _ = _create_temp_package(tmp_path, modules)
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            ids = [m.migration_id for m in result]
            assert ids == ["v1_0_0_a", "v2_0_0_m", "v2_0_0_z"]
        finally:
            sys.path.remove(str(tmp_path))

    def test_discover_multiple_migrations_in_one_module(
        self, tmp_path: Path
    ) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        source = '''\
from __future__ import annotations
from trackora.core.migration_manager import Migration


class FirstMigration(Migration):
    migration_id = "v2_0_0_first"
    description = "First"
    app_version = "2.0.0"

    def upgrade(self, connection: object) -> None:
        pass

    def downgrade(self, connection: object) -> None:
        pass


class SecondMigration(Migration):
    migration_id = "v2_0_0_second"
    description = "Second"
    app_version = "2.0.0"

    def upgrade(self, connection: object) -> None:
        pass

    def downgrade(self, connection: object) -> None:
        pass
'''
        pkg_name, _ = _create_temp_package(tmp_path, {"combined": source})
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            ids = sorted(m.migration_id for m in result)
            assert ids == ["v2_0_0_first", "v2_0_0_second"]
        finally:
            sys.path.remove(str(tmp_path))


class TestDiscoverIgnores:
    """Non-migration modules and abstract classes are skipped."""

    def test_discover_ignores_init_and_registry_modules(
        self, tmp_path: Path
    ) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        modules = {
            "__init__": "# just init\n",
            "registry": "# just registry placeholder\n",
            "v2_0_0_real": _migration_module("v2_0_0_real", "Real", "2.0.0"),
        }
        pkg_name, _ = _create_temp_package(tmp_path, modules)
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            assert len(result) == 1
            assert result[0].migration_id == "v2_0_0_real"
        finally:
            sys.path.remove(str(tmp_path))

    def test_discover_ignores_non_migration_classes(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        source = '''
from __future__ import annotations


class NotAMigration:
    """This class should not be discovered."""
    pass


class HelperUtility:
    """Also not a migration."""
    pass
'''
        modules = {"helpers": source}
        pkg_name, _ = _create_temp_package(tmp_path, modules)
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            assert result == []
        finally:
            sys.path.remove(str(tmp_path))


class TestGetById:
    """Lookup a migration by its migration_id."""

    def test_get_by_id_found(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        code = _migration_module("v2_0_0_findme", "Find me", "2.0.0")
        pkg_name, _ = _create_temp_package(tmp_path, {"findme": code})
        try:
            cls = MigrationRegistry.get_by_id(
                "v2_0_0_findme", package_name=pkg_name
            )
            assert cls is not None
            assert cls.migration_id == "v2_0_0_findme"
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_by_id_not_found_returns_none(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        pkg_name, _ = _create_temp_package(tmp_path, {})
        try:
            cls = MigrationRegistry.get_by_id(
                "nonexistent", package_name=pkg_name
            )
            assert cls is None
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_by_id_ignores_partial_match(self, tmp_path: Path) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        code = _migration_module("v2_0_0_exact", "Exact match", "2.0.0")
        pkg_name, _ = _create_temp_package(tmp_path, {"exact": code})
        try:
            cls = MigrationRegistry.get_by_id(
                "v2_0_0_ex", package_name=pkg_name
            )
            assert cls is None
        finally:
            sys.path.remove(str(tmp_path))
