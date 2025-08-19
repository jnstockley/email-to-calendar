from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from src import db_file

DATABASE_URL = f"sqlite:///{db_file}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
