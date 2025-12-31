from pathlib import Path

from src.util.env import get_settings

settings = get_settings()

db_file = Path(settings.DB_FILE)

db_file.parent.mkdir(parents=True, exist_ok=True)
