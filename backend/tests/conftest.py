import os
import tempfile

# Must be set BEFORE the app is imported: isolated DB, and never call the real EURI API in tests.
_tmp = tempfile.mkdtemp(prefix="kirai_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["EURI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Product  # noqa: E402
from app.seed import seed_database  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_parse_cache():
    from app.ai import parser

    parser._CACHE.clear()


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as session:
        seed_database(session, with_history=False)  # products + customers only: clean, predictable state
        yield session


@pytest.fixture()
def client(db):
    return TestClient(app)  # not used as a context manager -> lifespan (auto-seed) does not run


def set_stock(db, name: str, qty: int) -> None:
    product = db.query(Product).filter(Product.name == name).one()
    product.stock_quantity = qty
    db.commit()


def stock_of(db, name: str) -> int:
    db.expire_all()
    return db.query(Product).filter(Product.name == name).one().stock_quantity
