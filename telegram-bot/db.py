"""
Einfache SQLite-Datenschicht fuer den Telegram-Shop-Bot.
Fuer bis zu 50 Artikel voellig ausreichend, kein separater DB-Server noetig.
"""

import os
import random
import string
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, select

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////data/shop.db")
MAX_QTY_PER_ITEM = int(os.getenv("MAX_QTY_PER_ITEM", "5"))

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    price = Column(Float, nullable=False)
    image_url = Column(String, nullable=True)
    stock = Column(Integer, default=0)


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)


class Customer(Base):
    """Gespeicherte Kontaktdaten pro Telegram-Nutzer, fuer wiederkehrende Bestellungen."""
    __tablename__ = "customers"
    telegram_user_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_number = Column(String, unique=True, nullable=False)
    telegram_user_id = Column(Integer, nullable=False)
    total = Column(Float, nullable=False)
    summary = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    status = Column(String, default="offen")  # offen | angenommen | abgelehnt
    created_at = Column(DateTime, default=datetime.utcnow)


@dataclass
class CartItemView:
    product: Product
    quantity: int


class InsufficientStockError(Exception):
    """Wird ausgeloest, wenn nicht genug Lagerbestand fuer eine Bestellung vorhanden ist."""
    def __init__(self, product_name: str, available: int):
        self.product_name = product_name
        self.available = available
        super().__init__(f"Nicht genug Lagerbestand fuer {product_name}: nur noch {available} verfuegbar")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(select(Product))
        if not result.scalars().first():
            demo_products = [
                Product(name="Stoff-Schultuete Ninja", description="Beige mit Bausteinen-Motiv", price=34.90, stock=5),
                Product(name="Stoff-Schultuete Einhorn", description="Pinke Sterne, funkelnd", price=34.90, stock=5),
                Product(name="Stoff-Schultuete Dino", description="Mit Kopfhoerern, kindgerecht", price=34.90, stock=5),
            ]
            session.add_all(demo_products)
            await session.commit()


async def get_products() -> List[Product]:
    async with async_session() as session:
        result = await session.execute(select(Product).where(Product.stock > 0))
        return list(result.scalars().all())


async def get_product(product_id: int) -> Optional[Product]:
    async with async_session() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()


async def add_to_cart(telegram_user_id: int, product_id: int, quantity: int = 1) -> int:
    """
    Erhoeht/verringert die Menge im Warenkorb. Bei quantity <= 0 wird der Eintrag entfernt.
    Menge wird auf MAX_QTY_PER_ITEM und den aktuellen Lagerbestand begrenzt (Plausibilitaetspruefung).
    Gibt die tatsaechlich resultierende Menge zurueck.
    """
    async with async_session() as session:
        product_result = await session.execute(select(Product).where(Product.id == product_id))
        product = product_result.scalar_one_or_none()
        if not product:
            return 0

        result = await session.execute(
            select(CartItem).where(
                CartItem.telegram_user_id == telegram_user_id,
                CartItem.product_id == product_id,
            )
        )
        item = result.scalar_one_or_none()
        current_qty = item.quantity if item else 0
        new_qty = current_qty + quantity

        upper_limit = min(MAX_QTY_PER_ITEM, product.stock)
        new_qty = max(0, min(new_qty, upper_limit))

        if new_qty <= 0:
            if item:
                await session.delete(item)
        elif item:
            item.quantity = new_qty
        else:
            item = CartItem(telegram_user_id=telegram_user_id, product_id=product_id, quantity=new_qty)
            session.add(item)

        await session.commit()
        return new_qty


async def get_cart(telegram_user_id: int) -> List[CartItemView]:
    async with async_session() as session:
        result = await session.execute(
            select(CartItem).where(CartItem.telegram_user_id == telegram_user_id)
        )
        items = result.scalars().all()
        views = []
        for item in items:
            product = await get_product(item.product_id)
            if product:
                views.append(CartItemView(product=product, quantity=item.quantity))
        return views


async def clear_cart(telegram_user_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(CartItem).where(CartItem.telegram_user_id == telegram_user_id)
        )
        for item in result.scalars().all():
            await session.delete(item)
        await session.commit()


def _generate_order_number() -> str:
    date_part = datetime.utcnow().strftime("%y%m%d")
    rand_part = "".join(random.choices(string.digits, k=4))
    return f"LLD-{date_part}-{rand_part}"


async def validate_cart_stock(telegram_user_id: int) -> None:
    """
    Prueft vor dem Checkout, ob fuer alle Positionen im Warenkorb noch genug
    Lagerbestand vorhanden ist. Wirft InsufficientStockError, falls nicht.
    """
    items = await get_cart(telegram_user_id)
    for item in items:
        current_product = await get_product(item.product.id)
        if not current_product or current_product.stock < item.quantity:
            available = current_product.stock if current_product else 0
            raise InsufficientStockError(item.product.name, available)


# ---------------------------------------------------------------------
# Kundendaten (Name, E-Mail Pflicht, Telefon optional) - werden pro
# Telegram-Nutzer gespeichert, damit wiederkehrende Kunden sie nicht
# erneut eingeben muessen.
# ---------------------------------------------------------------------
async def get_customer(telegram_user_id: int) -> Optional[Customer]:
    async with async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()


async def save_customer(telegram_user_id: int, name: str, email: str, phone: Optional[str] = None) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.telegram_user_id == telegram_user_id)
        )
        customer = result.scalar_one_or_none()
        if customer:
            customer.name = name
            customer.email = email
            customer.phone = phone
        else:
            customer = Customer(
                telegram_user_id=telegram_user_id,
                name=name,
                email=email,
                phone=phone,
            )
            session.add(customer)
        await session.commit()


async def finalize_order(telegram_user_id: int, customer) -> Optional[dict]:
    """
    Schliesst eine Bestellung verbindlich ab:
    - prueft Lagerbestand erneut (Race-Condition-Schutz bei parallelen Bestellungen)
    - reduziert den Lagerbestand
    - erzeugt eine eindeutige Bestellnummer
    - speichert die Kontaktdaten bei der Bestellung (Snapshot zum Bestellzeitpunkt)
    - leert den Warenkorb
    Status der Bestellung ist zunaechst "offen" - Admin kann spaeter annehmen/ablehnen.
    Gibt None zurueck, wenn der Warenkorb leer ist oder Lagerbestand nicht mehr reicht.
    """
    async with async_session() as session:
        cart_result = await session.execute(
            select(CartItem).where(CartItem.telegram_user_id == telegram_user_id)
        )
        cart_items = cart_result.scalars().all()
        if not cart_items:
            return None

        order_lines = []
        total = 0.0

        for cart_item in cart_items:
            product_result = await session.execute(
                select(Product).where(Product.id == cart_item.product_id)
            )
            product = product_result.scalar_one_or_none()
            if not product or product.stock < cart_item.quantity:
                return None

            product.stock -= cart_item.quantity
            subtotal = product.price * cart_item.quantity
            total += subtotal
            order_lines.append(f"{cart_item.quantity}x {product.name}")

        order_number = _generate_order_number()
        order = Order(
            order_number=order_number,
            telegram_user_id=telegram_user_id,
            total=total,
            summary="\n".join(order_lines),
            customer_name=customer.name,
            customer_email=customer.email,
            customer_phone=customer.phone,
            status="offen",
        )
        session.add(order)

        for cart_item in cart_items:
            await session.delete(cart_item)

        await session.commit()

        return {
            "order_number": order_number,
            "total": total,
            "summary": "\n".join(order_lines),
        }


async def get_order_by_number(order_number: str) -> Optional[Order]:
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.order_number == order_number)
        )
        return result.scalar_one_or_none()


async def set_order_status(order_number: str, status: str) -> Optional[Order]:
    """status: 'angenommen' oder 'abgelehnt'"""
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.order_number == order_number)
        )
        order = result.scalar_one_or_none()
        if order:
            order.status = status
            await session.commit()
        return order
