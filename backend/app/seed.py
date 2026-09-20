"""Seed data. Run with:  python -m app.seed   (add --reset to wipe and re-seed)

Historical demo orders are created through the real order service, so their stock deductions,
inventory logs and activity logs are genuine. They are tagged source="seed" (not "ai_agent").
The order id sequence starts so the first live demo order becomes #1042.
"""
import sys
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, init_db
from app.models import Customer, Product
from app.services import order_service
from app.utils import ist_day_bounds, utcnow

# name, brand, category, unit, price, stock, low_threshold, aliases, description
PRODUCTS = [
    ("Aashirvaad Atta 5kg", "Aashirvaad", "Staples", "pack", 260, 40, 10, "atta, aata, flour, wheat flour, chakki atta", "Whole wheat flour, 100% atta from selected wheat."),
    ("Fortune Sunflower Oil 1L", "Fortune", "Oils", "pouch", 145, 30, 8, "fortune oil, refined oil, sunflower", "Refined sunflower oil, light and healthy."),
    ("Fortune Mustard Oil 1L", "Fortune", "Oils", "bottle", 165, 24, 8, "sarso, sarson, sarso oil, sarson ka tel, kachi ghani, mustard", "Kachi ghani mustard oil with strong aroma."),
    ("Maggi 70g", "Maggi", "Instant Food", "pack", 14, 60, 15, "maggi noodles, noodles, maggie, 2 minute noodles", "Maggi 2-minute masala noodles."),
    ("Tata Salt 1kg", "Tata", "Staples", "pack", 28, 50, 12, "namak, salt", "Vacuum evaporated iodised salt."),
    ("Amul Taaza Milk 1L", "Amul", "Dairy", "pouch", 56, 25, 8, "milk, doodh, dudh, toned milk", "Fresh toned milk, 1 litre pouch."),
    ("Parle-G Biscuits", "Parle", "Biscuits", "pack", 10, 80, 20, "parle g, parle-g, glucose biscuit, biscuit", "India's favourite glucose biscuits."),
    ("Tata Tea 250g", "Tata", "Beverages", "pack", 135, 30, 8, "tea, chai, chai patti", "Tata Tea Premium leaf tea."),
    ("Surf Excel 1kg", "Surf Excel", "Household", "pack", 125, 20, 6, "detergent, washing powder, surf", "Easy Wash detergent powder."),
    ("Dettol Soap 75g", "Dettol", "Personal Care", "piece", 45, 10, 10, "soap, sabun", "Original antibacterial bathing soap."),
    ("Colgate Toothpaste 200g", "Colgate", "Personal Care", "tube", 110, 25, 8, "toothpaste, paste, colgate", "Strong Teeth cavity protection toothpaste."),
    ("Britannia Bread", "Britannia", "Bakery", "pack", 45, 9, 8, "bread, double roti", "Soft sandwich bread, 400g."),
    ("Amul Butter 100g", "Amul", "Dairy", "pack", 58, 14, 10, "butter, makhan", "Pasteurised table butter."),
    ("Coca Cola 750ml", "Coca-Cola", "Cold Drinks", "bottle", 40, 36, 10, "coke, coca cola, cocacola", "Chilled cola, 750ml bottle."),
    ("Pepsi 750ml", "Pepsi", "Cold Drinks", "bottle", 40, 0, 10, "pepsi", "Refreshing cola, 750ml bottle."),
    ("Kissan Tomato Ketchup 500g", "Kissan", "Sauces", "bottle", 110, 18, 6, "ketchup, sauce, tomato sauce", "Fresh tomato ketchup."),
    ("Thums Up 750ml", "Thums Up", "Cold Drinks", "bottle", 40, 28, 10, "thumbs up, thums up, thumsup", "Strong cola, 750ml bottle."),
    ("Daawat Basmati Rice 5kg", "Daawat", "Staples", "pack", 649, 15, 5, "chawal, rice, basmati", "Aged long-grain basmati rice."),
    ("Toor Dal 1kg", "Store Brand", "Staples", "pack", 165, 22, 8, "dal, arhar, arhar dal, tur dal, toor", "Unpolished toor (arhar) dal."),
    ("Sugar 1kg", "Store Brand", "Staples", "pack", 48, 45, 10, "chini, cheeni, shakkar", "Fine crystal sugar."),
    ("Lay's Magic Masala 52g", "Lay's", "Snacks", "pack", 20, 40, 10, "chips, lays, wafers", "Crunchy potato chips, Magic Masala flavour."),
    ("Kurkure Masala Munch 90g", "Kurkure", "Snacks", "pack", 20, 7, 10, "chips, kurkure", "Crunchy masala corn puffs."),
]

CUSTOMERS = [
    ("Rahul Sharma", "9999999999", "Vijay Nagar, Indore"),
    ("Priya Verma", "9876543210", "Scheme No. 78, Indore"),
    ("Amit Patel", "9823456780", "Palasia, Indore"),
    ("Neha Joshi", "9811122233", "Saket Nagar, Indore"),
]

# (customer index, [(product name, qty)], days ago, minutes ago (today only), final status)
HISTORY = [
    (2, [("Thums Up 750ml", 2), ("Kurkure Masala Munch 90g", 3)], 4, 0, "delivered"),
    (3, [("Amul Butter 100g", 2), ("Britannia Bread", 3)], 5, 0, "delivered"),
    (0, [("Daawat Basmati Rice 5kg", 1), ("Sugar 1kg", 1)], 3, 0, "delivered"),
    (0, [("Aashirvaad Atta 5kg", 1), ("Toor Dal 1kg", 2), ("Fortune Sunflower Oil 1L", 1)], 1, 0, "delivered"),
    (1, [("Coca Cola 750ml", 3), ("Lay's Magic Masala 52g", 4)], 1, 0, "delivered"),
    (1, [("Maggi 70g", 4), ("Parle-G Biscuits", 5), ("Amul Taaza Milk 1L", 2)], 0, 190, "delivered"),
    (2, [("Tata Tea 250g", 1), ("Sugar 1kg", 2), ("Tata Salt 1kg", 1)], 0, 75, "out_for_delivery"),
    (3, [("Surf Excel 1kg", 1), ("Dettol Soap 75g", 2)], 0, 25, "confirmed"),
]

FIRST_ORDER_ID = 1034  # 8 history orders -> the next live order is #1042


def seed_database(db: Session, with_history: bool = True) -> dict:
    """Idempotent: does nothing if products already exist."""
    if db.scalar(select(Product.id).limit(1)) is not None:
        return {"seeded": False, "products": db.query(Product).count()}

    for name, brand, category, unit, price, stock, threshold, aliases, desc in PRODUCTS:
        db.add(Product(name=name, brand=brand, category=category, unit=unit, price=price, stock_quantity=stock,
                       low_stock_threshold=threshold, aliases=aliases, description=desc))
    for name, phone, address in CUSTOMERS:
        db.add(Customer(name=name, phone=phone, address=address))
    db.commit()

    orders = 0
    if with_history:
        if engine.dialect.name == "sqlite":
            db.execute(text("DELETE FROM sqlite_sequence WHERE name = 'orders'"))
            db.execute(text("INSERT INTO sqlite_sequence (name, seq) VALUES ('orders', :s)"), {"s": FIRST_ORDER_ID - 1})
            db.commit()
        customers = list(db.scalars(select(Customer).order_by(Customer.id)))
        by_name = {p.name: p.id for p in db.scalars(select(Product))}
        now = utcnow()
        today_start, _ = ist_day_bounds(0)
        for idx, (cust_i, lines, days_ago, mins_ago, status) in enumerate(HISTORY):
            if days_ago == 0:
                when = max(now - timedelta(minutes=mins_ago), today_start + timedelta(minutes=5 * (idx + 1)))
                when = min(when, now - timedelta(seconds=30))
            else:
                when = now - timedelta(days=days_ago, hours=(idx * 3) % 7)
            result = order_service.create_order(
                db,
                customers[cust_i].id,
                [{"product_id": by_name[n], "quantity": q} for n, q in lines],
                source="seed",
                created_at=when,
            )
            if status != "confirmed":
                result.order.status = status
                db.commit()
            orders += 1
    return {"seeded": True, "products": len(PRODUCTS), "customers": len(CUSTOMERS), "orders": orders}


def reset_database() -> dict:
    """Drop every table and rebuild the seed data (orders, items, logs, stock, customers)."""
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        return seed_database(db)


def main() -> None:
    if "--reset" in sys.argv:
        print("Reset:", reset_database())
        return
    init_db()
    with SessionLocal() as db:
        print("Seed:", seed_database(db))


if __name__ == "__main__":
    main()
