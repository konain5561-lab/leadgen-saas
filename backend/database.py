"""DB engine + session setup.

Defaults to a local SQLite file so you can run the API with zero
external setup while developing. Swap DATABASE_URL to a Postgres
connection string for anything beyond local testing -- the ORM code
is identical either way.

    export DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/leadsdb"
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./leads.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
