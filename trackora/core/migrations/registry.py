"""MigrationRegistry — auto-discovers Migration subclasses.

Scans a given Python package for concrete Migration subclasses,
sorts them by migration_id, and provides lookup by ID.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trackora.core.migration_manager import Migration

logger = logging.getLogger(__name__)

_DEFAULT_MIGRATIONS_PACKAGE = "trackora.core.migrations"

_SKIP_MODULES = frozenset({"__init__", "registry"})


class MigrationRegistry:
    """Discovers and orders Migration subclasses.

    Typical usage::

        registry = MigrationRegistry()
        pending = registry.discover()

    Or with a custom package (for testing)::

        registry = MigrationRegistry()
        result = registry.discover(package_name="my_test_migrations")
    """

    @classmethod
    def discover(
        cls,
        package_name: str | None = None,
    ) -> list[type[Migration]]:
        """Scan *package_name* for concrete Migration subclasses.

        Args:
            package_name: The dotted package name to scan.
                          Defaults to ``trackora.core.migrations``.

        Returns:
            Sorted list of Migration classes (ascending by ``migration_id``).
        """
        from trackora.core.migration_manager import Migration

        if package_name is None:
            package_name = _DEFAULT_MIGRATIONS_PACKAGE

        try:
            package = importlib.import_module(package_name)
        except (ImportError, ModuleNotFoundError):
            logger.warning("Migration package not found: %s", package_name)
            return []

        package_path = getattr(package, "__file__", None)
        if package_path is None:
            return []

        package_dir = Path(package_path).parent
        migrations: list[type[Migration]] = []

        for _importer, modname, _is_pkg in pkgutil.iter_modules(
            [str(package_dir)]
        ):
            if modname in _SKIP_MODULES:
                continue

            try:
                module = importlib.import_module(f"{package_name}.{modname}")
            except ImportError as exc:
                logger.warning("Cannot import migration module %s: %s", modname, exc)
                continue

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    obj is not Migration
                    and issubclass(obj, Migration)
                    and not inspect.isabstract(obj)
                ):
                    migrations.append(obj)

        migrations.sort(key=lambda m: m.migration_id)
        logger.debug("Discovered %d migrations in %s", len(migrations), package_name)
        return migrations

    @classmethod
    def get_by_id(
        cls,
        migration_id: str,
        package_name: str | None = None,
    ) -> type[Migration] | None:
        """Look up a migration class by its ``migration_id``.

        Args:
            migration_id: The migration identifier to find.
            package_name: Optional custom package to scan.

        Returns:
            The Migration class, or ``None`` if not found.
        """
        for m in cls.discover(package_name=package_name):
            if m.migration_id == migration_id:
                return m
        return None
