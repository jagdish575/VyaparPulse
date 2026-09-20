"""Inventory + product matching. The database is the single source of truth for stock and price."""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import InsufficientStockError, NotFoundError
from app.models import InventoryLog, Product
from app.utils import money, utcnow

# ----------------------------------------------------------------------------- text helpers

SIZE_TOKEN = re.compile(r"^\d+(?:\.\d+)?(?:g|gm|kg|ml|l|ltr)$")

# Words that describe quantity/units/politeness rather than the product itself.
QUERY_NOISE = {
    "packet", "packets", "pkt", "pkts", "pack", "packs", "pouch", "bottle", "bottles", "piece", "pieces",
    "pc", "pcs", "dabba", "litre", "liter", "ltr", "l", "kg", "gm", "gram", "grams", "g", "ml",
    "of", "the", "a", "an", "some", "ka", "ki", "ke", "wala", "wali", "one",
}


def tokenize(text: str) -> list[str]:
    text = (text or "").lower().replace("'", "").replace("’", "")
    return re.findall(r"[a-z0-9]+", text)


def stem(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


def query_tokens(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text) if t not in QUERY_NOISE and not t.isdigit()]


def stock_status(stock: int, threshold: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    if stock <= threshold:
        return "low_stock"
    return "in_stock"


# ----------------------------------------------------------------------------- matching

def _profile(p: Product) -> tuple[set[str], set[tuple[str, ...]]]:
    """(searchable tokens, exact phrases) for a product."""
    name_tokens = [stem(t) for t in tokenize(p.name)]
    nosize = tuple(t for t in name_tokens if not SIZE_TOKEN.match(t))
    tokens = set(name_tokens) | {stem(t) for t in tokenize(p.brand)} | {stem(t) for t in tokenize(p.category)}
    phrases: set[tuple[str, ...]] = {tuple(name_tokens), nosize}
    for alias in (p.aliases or "").split(","):
        alias_tokens = tuple(stem(t) for t in tokenize(alias))
        if alias_tokens:
            phrases.add(alias_tokens)
            tokens.update(alias_tokens)
    return tokens, phrases


def _token_hit(q: str, tokens: set[str], prefix: bool = False) -> float:
    if q in tokens:
        return 1.0
    if prefix and len(q) >= 2 and any(t.startswith(q) for t in tokens):
        return 0.8
    if len(q) >= 4:  # typo tolerance ("aashirwad" ~ "aashirvaad")
        for t in tokens:
            if len(t) >= 4 and abs(len(t) - len(q)) <= 2 and SequenceMatcher(None, q, t).ratio() >= 0.84:
                return 0.9
    return 0.0


def _coverage(qt: list[str], tokens: set[str], prefix: bool = False) -> float:
    if not qt:
        return 0.0
    return sum(_token_hit(q, tokens, prefix) for q in qt) / len(qt)


def _active_products(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.name)))


def search_products(db: Session, query: str, limit: int = 10) -> list[Product]:
    """Ranked product search (used by the API and the search_products tool)."""
    qt = query_tokens(query)
    if not qt:
        return []
    ranked: list[tuple[float, Product]] = []
    for p in _active_products(db):
        tokens, phrases = _profile(p)
        cov = _coverage(qt, tokens, prefix=True)
        if cov <= 0:
            continue
        score = cov + (1.0 if tuple(qt) in phrases else 0.0)
        ranked.append((score, p))
    ranked.sort(key=lambda x: (-x[0], x[1].name))
    return [p for _, p in ranked[:limit]]


@dataclass
class Resolution:
    query: str
    status: str  # matched | ambiguous | not_found
    product: Product | None = None
    options: list[Product] = field(default_factory=list)
    suggestions: list[Product] = field(default_factory=list)


def _suggest(products: list[Product], qt: list[str], hint: str | None, limit: int = 3) -> list[Product]:
    hint_tokens = query_tokens(hint) if hint else []
    scored: list[tuple[float, Product]] = []
    for p in products:
        tokens, _ = _profile(p)
        score = _coverage(qt, tokens)
        if qt:
            name_sim = SequenceMatcher(None, " ".join(qt), " ".join(t for t in tokenize(p.name) if not SIZE_TOKEN.match(t))).ratio()
            if name_sim >= 0.6:
                score = max(score, name_sim)
        if hint_tokens and _coverage(hint_tokens, tokens) >= 1.0:
            score += 0.5
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return [p for _, p in scored[:limit]]


def resolve_product(db: Session, query: str, category_hint: str | None = None) -> Resolution:
    """Map a customer's product phrase to a real product.

    matched   -> exactly one product fits (exact alias/name wins over looser matches)
    ambiguous -> several products fit; the customer must choose (we never guess)
    not_found -> nothing fits; nearby products are returned as suggestions
    """
    products = _active_products(db)
    qt = query_tokens(query)
    if not qt:
        return Resolution(query, "not_found", suggestions=_suggest(products, qt, category_hint))

    profiles = {p.id: _profile(p) for p in products}
    candidates = [p for p in products if _all_tokens_hit(qt, profiles[p.id][0])]
    if not candidates:
        return Resolution(query, "not_found", suggestions=_suggest(products, qt, category_hint))

    exact = [p for p in candidates if tuple(qt) in profiles[p.id][1]]
    if len(exact) == 1:
        return Resolution(query, "matched", product=exact[0])
    pool = exact if len(exact) > 1 else candidates
    if len(pool) == 1:
        return Resolution(query, "matched", product=pool[0])
    return Resolution(query, "ambiguous", options=sorted(pool, key=lambda p: p.name))


def _all_tokens_hit(qt: list[str], tokens: set[str]) -> bool:
    return all(_token_hit(q, tokens) > 0 for q in qt)


def resolve_products(db: Session, names: list[str]) -> list[Resolution]:
    return [resolve_product(db, n) for n in names]


def choose_from_options(reply: str, options: list[Product]) -> Product | None:
    """Interpret a clarification reply ("2", "sunflower", "pehla") against a list of options."""
    text = reply.strip().lower()
    ordinals = {"1": 0, "first": 0, "1st": 0, "pehla": 0, "pehli": 0, "2": 1, "second": 1, "2nd": 1, "dusra": 1,
                "dusri": 1, "3": 2, "third": 2, "3rd": 2, "teesra": 2, "teesri": 2, "4": 3, "fourth": 3, "chautha": 3}
    stripped = re.sub(r"[^\w\s]", "", text).strip()
    if stripped in ordinals and ordinals[stripped] < len(options):
        return options[ordinals[stripped]]
    qt = query_tokens(text)
    if not qt:
        return None
    matches = [p for p in options if _all_tokens_hit(qt, _profile(p)[0])]
    return matches[0] if len(matches) == 1 else None


# ----------------------------------------------------------------------------- reads

def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("That product could not be found.")
    return product


def list_products(
    db: Session,
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    include_inactive: bool = False,
) -> list[Product]:
    if q and q.strip():
        products = search_products(db, q, limit=100)
    else:
        stmt = select(Product).order_by(Product.category, Product.name)
        products = list(db.scalars(stmt))
    if not include_inactive:
        products = [p for p in products if p.is_active]
    if category:
        products = [p for p in products if p.category.lower() == category.lower()]
    if status:
        products = [p for p in products if stock_status(p.stock_quantity, p.low_stock_threshold) == status]
    return products


def list_categories(db: Session) -> list[str]:
    return sorted({c for c in db.scalars(select(Product.category))})


def get_inventory(db: Session, product_id: int) -> dict:
    p = get_product(db, product_id)
    return {
        "product_id": p.id,
        "name": p.name,
        "unit": p.unit,
        "price": money(p.price),
        "stock_quantity": p.stock_quantity,
        "low_stock_threshold": p.low_stock_threshold,
        "status": stock_status(p.stock_quantity, p.low_stock_threshold),
    }


def low_stock_products(db: Session) -> list[Product]:
    products = [
        p for p in _active_products(db) if stock_status(p.stock_quantity, p.low_stock_threshold) != "in_stock"
    ]
    return sorted(products, key=lambda p: (p.stock_quantity, p.name))


def inventory_summary(db: Session) -> dict:
    products = _active_products(db)
    counts = {"in_stock": 0, "low_stock": 0, "out_of_stock": 0}
    for p in products:
        counts[stock_status(p.stock_quantity, p.low_stock_threshold)] += 1
    return {
        "total_products": len(products),
        **counts,
        "total_units": sum(p.stock_quantity for p in products),
        "stock_value": money(sum(p.stock_quantity * p.price for p in products)),
    }


def product_logs(db: Session, product_id: int, limit: int = 15) -> list[InventoryLog]:
    stmt = (
        select(InventoryLog)
        .where(InventoryLog.product_id == product_id)
        .order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


# ----------------------------------------------------------------------------- writes (no commit here)

def deduct_stock(db: Session, product_id: int, quantity: int, order_id: int | None, now=None) -> InventoryLog:
    """Atomically deduct stock. The conditional UPDATE guarantees stock can never go negative,
    even under concurrent requests. The caller owns the transaction (commit / rollback)."""
    now = now or utcnow()
    result = db.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock_quantity >= quantity)
        .values(stock_quantity=Product.stock_quantity - quantity, updated_at=now)
    )
    product = db.get(Product, product_id)
    if result.rowcount != 1:
        db.refresh(product)
        raise InsufficientStockError(product.name, product.stock_quantity, quantity)
    db.refresh(product)
    log = InventoryLog(
        product=product,  # set the relationship too: the row is not flushed yet, so it can't lazy-load
        product_id=product_id,
        order_id=order_id,
        change_type="order_deduction",
        quantity_change=-quantity,
        stock_before=product.stock_quantity + quantity,
        stock_after=product.stock_quantity,
        created_at=now,
    )
    db.add(log)
    return log
