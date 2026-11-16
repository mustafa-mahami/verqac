from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.models.core import Base
import app.models.records  # noqa: F401  (registers the record tables)
import app.models.structure  # noqa: F401

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().migration_database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
