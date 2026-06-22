"""trackora.core.migrations — schema migration package.

Each module in this package exports a concrete Migration subclass.
Migratons are auto-discovered by MigrationRegistry at startup.
"""

from __future__ import annotations

# Explicit imports ensure PyInstaller bundles every migration module
# so that MigrationRegistry.discover() can find them in frozen mode.
from trackora.core.migrations import (
    v1_0_0_base_schema,
    v1_1_0_initial_schema,
    v2_0_0_add_discovery_columns,
    v2_0_0_add_update_center_settings,
    v2_0_0_add_update_center_settings_v2,
)
