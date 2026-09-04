#!/usr/bin/env python3
"""Integration tests for the Telegram Shop Bot ordering flow."""
import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import sys
sys.path.insert(0, "telegram-bot")

test_db = os.path.join(tempfile.gettempdir(), "test_shop.db")
TEST_DB_URL = f"sqlite+aiosqlite:///{test_db}"
os.environ["DATABASE_URL"] = TEST_DB_URL

from db import Base, Product, CartItem, Customer, Order, add_to_cart, get_cart, validate_cart_stock, finalize_order, clear_cart, save_customer, get_customer, InsufficientStockError, get_products_by_category, get_categories, search_products, get_featured_products

@pytest_asyncio.fixture
async def patched_db():
    if os.path.exists(test_db):
        os.remove(test_db)
    test_eng = create_async_engine(TEST_DB_URL, echo=False)
    async with test_eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session_factory = sessionmaker(test_eng, class_=AsyncSession, expire_on_commit=False)
    with patch("db.engine", test_eng), patch("db.async_session", test_session_factory):
        yield test_session_factory, test_eng
    await test_eng.dispose()
    if os.path.exists(test_db):
        os.remove(test_db)

@pytest_asyncio.fixture
async def seeded_db(patched_db):
    factory, _ = patched_db
    async with factory() as session:
        products = [Product(name="Test Schultute 1", price=29.90, stock=5), Product(name="Test Schultute 2", price=34.90, stock=3), Product(name="Test Schultute 3", price=19.90, stock=10)]
        session.add_all(products)
        await session.commit()
        for p in products:
            await session.refresh(p)
        return products

class TestCartOperations:
    @pytest.mark.asyncio
    async def test_add_to_cart(self, patched_db, seeded_db):
        user_id = 12345
        product = seeded_db[0]
        qty = await add_to_cart(user_id, product.id, quantity=2)
        assert qty == 2
        cart = await get_cart(user_id)
        assert len(cart) == 1
        assert cart[0].quantity == 2

    @pytest.mark.asyncio
    async def test_add_increases_quantity(self, patched_db, seeded_db):
        user_id = 12346
        product = seeded_db[0]
        await add_to_cart(user_id, product.id, quantity=1)
        await add_to_cart(user_id, product.id, quantity=1)
        cart = await get_cart(user_id)
        assert len(cart) == 1
        assert cart[0].quantity == 2

    @pytest.mark.asyncio
    async def test_clear_cart(self, patched_db, seeded_db):
        user_id = 12347
        await add_to_cart(user_id, seeded_db[0].id, quantity=3)
        await clear_cart(user_id)
        cart = await get_cart(user_id)
        assert len(cart) == 0

    @pytest.mark.asyncio
    async def test_multiple_products(self, patched_db, seeded_db):
        user_id = 12348
        for p in seeded_db:
            await add_to_cart(user_id, p.id, quantity=1)
        cart = await get_cart(user_id)
        assert len(cart) == 3

class TestOrderFlow:
    @pytest.mark.asyncio
    async def test_finalize_order(self, patched_db, seeded_db):
        user_id = 12351
        product = seeded_db[2]
        await add_to_cart(user_id, product.id, quantity=2)
        await save_customer(user_id, "Test User", "test@example.com", "+49123456789")
        customer = await get_customer(user_id)
        order = await finalize_order(user_id, customer)
        assert order is not None
        assert order["order_number"].startswith("LLD-")
        assert order["total"] == 39.80

    @pytest.mark.asyncio
    async def test_finalize_order_clears_cart(self, patched_db, seeded_db):
        user_id = 12352
        await add_to_cart(user_id, seeded_db[0].id, quantity=1)
        await save_customer(user_id, "Test User", "test@example.com")
        customer = await get_customer(user_id)
        await finalize_order(user_id, customer)
        cart = await get_cart(user_id)
        assert len(cart) == 0

    @pytest.mark.asyncio
    async def test_finalize_reduces_stock(self, patched_db, seeded_db):
        from db import get_product
        user_id = 12353
        product = seeded_db[0]
        original_stock = product.stock
        await add_to_cart(user_id, product.id, quantity=1)
        await save_customer(user_id, "Test User", "test@example.com")
        customer = await get_customer(user_id)
        await finalize_order(user_id, customer)
        updated = await get_product(product.id)
        assert updated.stock == original_stock - 1

class TestCategoriesSearchFeatured:
    @pytest.mark.asyncio
    async def test_get_categories(self, seeded_db):
        cats = await get_categories()
        assert isinstance(cats, list)

    @pytest.mark.asyncio
    async def test_get_products_by_category(self, seeded_db):
        product = seeded_db[0]
        category = product.category
        results = await get_products_by_category(category)
        assert len(results) >= 1
        assert all(p.category == category for p in results)

    @pytest.mark.asyncio
    async def test_get_products_by_category_nonexistent(self, seeded_db):
        results = await get_products_by_category("NichtExistent123")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_products_by_name(self, seeded_db):
        results = await search_products("Schultute")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_products_case_insensitive(self, seeded_db):
        results = await search_products("schultute")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_products_no_match(self, seeded_db):
        results = await search_products("XYZABC123")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_featured_products(self, seeded_db):
        results = await get_featured_products(limit=2)
        assert len(results) <= 2
        assert all(p.stock > 0 for p in results)

    @pytest.mark.asyncio
    async def test_featured_products_respect_limit(self, seeded_db):
        results = await get_featured_products(limit=1)
        assert len(results) <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
