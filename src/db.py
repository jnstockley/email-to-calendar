from sqlmodel import create_engine, Session

from src.util.env import get_settings

settings = get_settings()

DATABASE_URL = f"sqlite:///{settings.DB_FILE}"

engine = create_engine(DATABASE_URL)


def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
