import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# SQLite needs the parent directory to exist before the engine opens the file.
if settings.database_url.startswith("sqlite:///"):
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.entities import models  # noqa: F401  (registers mappers before create_all)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Add columns that exist in the models but not yet in the database file.

    There is no migration tool here: ``create_all`` creates missing *tables* but
    never alters existing ones, so a database created before a new column was
    added would break on the next query. Adding columns is the only schema
    change this project has needed, and it is the one change SQLite can always
    do in place - anything more involved should get a real migration tool.
    """
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(engine.dialect)}"
            try:
                with engine.begin() as connection:
                    connection.execute(text(ddl))
                logger.info("Added missing column %s.%s", table.name, column.name)
            except SQLAlchemyError:
                logger.exception("Could not add column %s.%s", table.name, column.name)
