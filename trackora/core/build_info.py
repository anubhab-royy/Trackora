from __future__ import annotations

from trackora import __version__
from trackora.core.environment import CURRENT_ENVIRONMENT

BUILD_CHANNEL: str = CURRENT_ENVIRONMENT.value
BUILD_VERSION: str = __version__
