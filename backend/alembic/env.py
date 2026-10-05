from sqlalchemy import create_engine

from alembic import context
from app.auth.models import User  # noqa: F401
from app.common.config import get_settings
from app.db.base import Base
from app.events.models import Event  # noqa: F401


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(
            url=get_settings().sqlalchemy_url,
            target_metadata=Base.metadata,
            literal_binds=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(get_settings().sqlalchemy_url)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
