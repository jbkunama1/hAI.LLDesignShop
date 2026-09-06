"""Delete all products marked as test-article. Run with --yes to skip confirmation."""
import asyncio
import argparse

from sqlalchemy import select, delete

from db import init_db, async_session, Product


async def delete_test_products(yes: bool = False) -> int:
    await init_db()
    async with async_session() as session:
        result = await session.execute(
            select(Product).where(Product.category == "test-article")
        )
        products = result.scalars().all()
        if not products:
            print("No test-article products found.")
            return 0

        print(f"Found {len(products)} test-article product(s):")
        for p in products:
            print(f"  - id={p.id} | {p.name} | €{p.price}")

        if not yes:
            answer = input("\nDelete all? Type 'yes' to confirm: ").strip().lower()
            if answer != "yes":
                print("Aborted.")
                return 0

        await session.execute(
            delete(Product).where(Product.category == "test-article")
        )
        await session.commit()
        print(f"\nDeleted {len(products)} test-article product(s).")
        return len(products)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()
    asyncio.run(delete_test_products(yes=args.yes))
