"""Tests for Migration ABC — validation, subclass contract, and defaults."""

from __future__ import annotations

import re
from abc import ABC

import pytest

_MIGRATION_ID_PATTERN = re.compile(r"^v\d+_\d+_\d+_[a-z0-9_]+$")


class TestMigrationIsAbstract:
    """Migration cannot be instantiated directly."""

    def test_cannot_instantiate_abstract(self) -> None:
        from trackora.core.migration_manager import Migration

        with pytest.raises(TypeError):
            Migration()  # type: ignore[abstract]


class TestConcreteMigration:
    """A valid concrete subclass must work."""

    def test_valid_subclass_can_be_instantiated(self) -> None:
        from trackora.core.migration_manager import Migration

        class ValidMigration(Migration):
            migration_id = "v2_0_0_test_migration"
            description = "A valid test migration"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        instance = ValidMigration()
        assert instance.migration_id == "v2_0_0_test_migration"
        assert instance.description == "A valid test migration"
        assert instance.app_version == "2.0.0"

    def test_requires_backup_defaults_to_true(self) -> None:
        from trackora.core.migration_manager import Migration

        class TestMigration(Migration):
            migration_id = "v2_0_0_test_backup"
            description = "Test requires_backup default"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        assert TestMigration().requires_backup is True

    def test_requires_backup_can_be_overridden(self) -> None:
        from trackora.core.migration_manager import Migration

        class NoBackupMigration(Migration):
            migration_id = "v2_0_0_no_backup"
            description = "Migration that does not need backup"
            app_version = "2.0.0"
            requires_backup = False

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        assert NoBackupMigration().requires_backup is False

    def test_verify_defaults_to_empty_list(self) -> None:
        from trackora.core.migration_manager import Migration

        class TestMigration(Migration):
            migration_id = "v2_0_0_test_verify"
            description = "Test verify default"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        assert TestMigration().verify("connection") == []

    def test_verify_can_be_overridden(self) -> None:
        from trackora.core.migration_manager import Migration

        class VerifyingMigration(Migration):
            migration_id = "v2_0_0_verify"
            description = "Migration with custom verify"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

            def verify(self, connection: object) -> list[str]:
                return ["column X not found"]

        assert VerifyingMigration().verify("connection") == ["column X not found"]

    def test_requires_downtime_defaults_to_false(self) -> None:
        from trackora.core.migration_manager import Migration

        class TestMigration(Migration):
            migration_id = "v2_0_0_downtime"
            description = "Test requires_downtime default"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        assert TestMigration().requires_downtime is False

    def test_is_subclass_of_abc(self) -> None:
        from trackora.core.migration_manager import Migration

        assert issubclass(Migration, ABC)

    def test_default_source_checksum(self) -> None:
        from trackora.core.migration_manager import Migration

        class TestMigration(Migration):
            migration_id = "v2_0_0_checksum"
            description = "Test checksum"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        result = TestMigration().source_checksum()
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in result)


class TestInvalidMigration:
    """Subclasses missing required attributes must raise at instantiation."""

    def test_missing_migration_id_raises(self) -> None:
        from trackora.core.migration_manager import Migration

        with pytest.raises(TypeError):

            class BadMigration(Migration):
                description = "Missing migration_id"
                app_version = "2.0.0"

                def upgrade(self, connection: object) -> None:
                    pass

                def downgrade(self, connection: object) -> None:
                    pass

            BadMigration()

    def test_missing_description_raises(self) -> None:
        from trackora.core.migration_manager import Migration

        with pytest.raises(TypeError):

            class BadMigration(Migration):
                migration_id = "v2_0_0_bad"
                app_version = "2.0.0"

                def upgrade(self, connection: object) -> None:
                    pass

                def downgrade(self, connection: object) -> None:
                    pass

            BadMigration()

    def test_missing_app_version_raises(self) -> None:
        from trackora.core.migration_manager import Migration

        with pytest.raises(TypeError):

            class BadMigration(Migration):
                migration_id = "v2_0_0_bad"
                description = "Missing app_version"

                def upgrade(self, connection: object) -> None:
                    pass

                def downgrade(self, connection: object) -> None:
                    pass

            BadMigration()

    def test_missing_upgrade_raises(self) -> None:
        from trackora.core.migration_manager import Migration

        with pytest.raises(TypeError):

            class BadMigration(Migration):
                migration_id = "v2_0_0_bad"
                description = "Missing upgrade"
                app_version = "2.0.0"

                def downgrade(self, connection: object) -> None:
                    pass

            BadMigration()

    def test_missing_downgrade_raises(self) -> None:
        from trackora.core.migration_manager import Migration

        with pytest.raises(TypeError):

            class BadMigration(Migration):
                migration_id = "v2_0_0_bad"
                description = "Missing downgrade"
                app_version = "2.0.0"

                def upgrade(self, connection: object) -> None:
                    pass

            BadMigration()


class TestMigrationIdValidation:
    """migration_id must match the required pattern."""

    def test_valid_migration_id_passes(self) -> None:
        from trackora.core.migration_manager import Migration

        valid_ids = [
            "v2_0_0_add_discovery_columns",
            "v1_0_0_base_schema",
            "v2_1_0_add_game_tags",
            "v10_0_0_major_update",
            "v0_0_1_initial",
            "v2_0_0_a",
        ]
        for vid in valid_ids:
            assert _MIGRATION_ID_PATTERN.match(vid), f"Expected {vid!r} to match"

    def test_invalid_migration_id_fails_pattern(self) -> None:
        invalid_ids = [
            "2_0_0_no_v_prefix",
            "v2_0_no_patch",
            "v2_0_0_UpperCase",
            "v2.0.0_dots",
            "v2-0-0_hyphens",
            "v2_0_0_ spaces",
            "_v2_0_0_leading_underscore",
            "V2_0_0_caps",
            "v_0_0_leading_underscore_version",
        ]
        for iid in invalid_ids:
            assert not _MIGRATION_ID_PATTERN.match(iid), f"Expected {iid!r} to NOT match"
