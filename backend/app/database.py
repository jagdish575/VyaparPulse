from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")  # enforce FK constraints
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)
    from app import ledger_models  # noqa: F401
    from sqlalchemy import select

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # Additive bootstrap: never infer settlement of existing orders or rewrite them.
        if conn.scalar(select(ledger_models.LedgerState.id)) is None:
            from sqlalchemy.exc import IntegrityError
            try:
                with conn.begin_nested():
                    conn.execute(ledger_models.LedgerState.__table__.insert().values(id=1, revision=0))
            except IntegrityError:
                pass  # another worker completed the same bootstrap
