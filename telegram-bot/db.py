"""
Einfache SQLite-Datenschicht fuer den Telegram-Shop-Bot.
Fuer bis zu 50 Artikel voellig ausreichend, kein separater DB-Server noetig.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, select

raw_db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////data/shop.db")
if raw_db_url.startswith("sqlite://") and not raw_db_url.startswith("sqlite+"):
    DATABASE_URL = raw_db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
else:
    DATABASE_URL = raw_db_url

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


@dataclass
class CartItemView:
    product: Product
    quantity: int


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Beispielprodukte nur einfuegen, wenn Katalog leer ist
    async with async_session() as session:
        result = await session.execute(select(Product))
        if not result.scalars().first():
            demo_products = [
                Product(name="Beispiel-Artikel 1", description="Beschreibung hier einfuegen", price=19.90, stock=10),
                Product(name="Beispiel-Artikel 2", description="Beschreibung hier einfuegen", price=24.90, stock=5),
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


async def add_to_cart(telegram_user_id: int, product_id: int, quantity: int = 1):
    async with async_session() as session:
        result = await session.execute(
            select(CartItem).where(
                CartItem.telegram_user_id == telegram_user_id,
                CartItem.product_id == product_id,
            )
        )
        item = result.scalar_one_or_none()
        if item:
            item.quantity += quantity
        else:
            item = CartItem(telegram_user_id=telegram_user_id, product_id=product_id, quantity=quantity)
            session.add(item)
        await session.commit()


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
