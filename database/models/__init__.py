"""
database.models
~~~~~~~~~~~~~~~
Dataclass models that mirror the GameTracker database schema (v1.0).

Public API:
    Game
    Session
    ActiveSession
    Setting
"""

from database.models.game import Game
from database.models.session import Session
from database.models.active_session import ActiveSession
from database.models.setting import Setting

__all__ = [
    "Game",
    "Session",
    "ActiveSession",
    "Setting",
]