from sqlalchemy import create_engine

import app.models  # noqa: F401
from alembic import context
from app.config import get_settings
from app.database import Base

url = get_settings().jobs_database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
