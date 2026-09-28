from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from engine.db.models import Base
from engine.settings import get_settings


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _pragma(conn, _):  # WAL lets the API read while jobs write
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return eng


@lru_cache(maxsize=4)
def _factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    s = _factory(url)()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db(url: str | None = None) -> None:
    """Create tables directly (dev/tests). Production uses `alembic upgrade head`."""
    Base.metadata.create_all(get_engine(url))


def reset_db_caches() -> None:
    get_engine.cache_clear()
    _factory.cache_clear()
