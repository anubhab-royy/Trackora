# Package Entry Point

"""
database
~~~~~~~~
GameTracker database layer.

Entry point is DatabaseManager. Consumers should:
    1. Instantiate DatabaseManager(db_path=...)
    2. Call .initialize()
    3. Pass .connection to individual repositories

Example:
    from database import DatabaseManager
    from database.repositories import GamesRepository

    db = DatabaseManager()
    db.initialize()
    games_repo = GamesRepository(db.connection)
"""

from database.database_manager import DatabaseManager

__all__ = ["DatabaseManager"]