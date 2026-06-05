from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def ensure_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(tasks)")).fetchall()}
        migrations = {
            "agent_id": "ALTER TABLE tasks ADD COLUMN agent_id VARCHAR(120)",
            "agent_run_id": "ALTER TABLE tasks ADD COLUMN agent_run_id VARCHAR(120)",
            "agent_claimed_at": "ALTER TABLE tasks ADD COLUMN agent_claimed_at DATETIME",
        }
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
