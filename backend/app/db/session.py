from typing import Generator
from sqlmodel import create_engine, Session
from app.core.config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine_kwargs = {
    "echo": False,
    "future": True,
    "connect_args": connect_args,
    "pool_pre_ping": not is_sqlite,
}
if not is_sqlite:
    engine_kwargs["pool_recycle"] = 300

# Create database engine with SQLAlchemy 2.0 behaviors enabled
engine = create_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)

def get_session() -> Generator[Session, None, None]:
    """
    Dependency helper to yield database sessions for requests.
    """
    with Session(engine) as session:
        yield session
