from typing import Generator
from sqlmodel import create_engine, Session
from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Create database engine with SQLAlchemy 2.0 behaviors enabled
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=not settings.DATABASE_URL.startswith("sqlite"),
)

def get_session() -> Generator[Session, None, None]:
    """
    Dependency helper to yield database sessions for requests.
    """
    with Session(engine) as session:
        yield session
