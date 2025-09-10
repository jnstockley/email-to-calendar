from sqlmodel import create_engine, Session

from src import db_file

DATABASE_URL = f"sqlite:///{db_file}"

engine = create_engine(DATABASE_URL)


def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
