from sqlalchemy import create_engine

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.models import Profile, User  # noqa: F401

url = get_settings().database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
