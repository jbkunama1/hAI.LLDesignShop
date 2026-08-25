"""
Optionales Abgleich-Skript: Produkte aus EverShop (GraphQL) in die
lokale Telegram-Bot-Datenbank importieren, damit du den Katalog nur
einmal in EverShop pflegen musst.

Nutzung (innerhalb des Bot-Containers oder lokal mit gesetztem EVERSHOP_GRAPHQL_URL):
    python sync_evershop.py

Empfehlung: als Cronjob / GitHub Action periodisch laufen lassen,
oder manuell nach Katalogaenderungen in EverShop ausfuehren.
"""

import asyncio
import os

import httpx

from db import init_db, async_session, Product
from sqlalchemy import select

EVERSHOP_GRAPHQL_URL = os.getenv("EVERSHOP_GRAPHQL_URL", "http://evershop:3000/graphql")

QUERY = """
query {
  products(filters: []) {
    items {
      productId
      name
      description
      price { regular { value } }
      image { url }
      inventory { qty }
    }
  }
}
"""


async def sync():
    await init_db()

    async with httpx.AsyncClient() as client:
        response = await client.post(EVERSHOP_GRAPHQL_URL, json={"query": QUERY}, timeout=30)
        response.raise_for_status()
        data = response.json()

    items = data.get("data", {}).get("products", {}).get("items", [])

    async with async_session() as session:
        for item in items:
            result = await session.execute(
                select(Product).where(Product.name == item["name"])
            )
            product = result.scalar_one_or_none()

            price = item.get("price", {}).get("regular", {}).get("value", 0)
            stock = item.get("inventory", {}).get("qty", 0)
            image = item.get("image", {}).get("url") if item.get("image") else None
            description = item.get("description", "") or ""

            if product:
                product.price = price
                product.stock = stock
                product.image_url = image
                product.description = description
            else:
                session.add(
                    Product(
                        name=item["name"],
                        description=description,
                        price=price,
                        stock=stock,
                        image_url=image,
                    )
                )
        await session.commit()

    print(f"Sync abgeschlossen: {len(items)} Produkte verarbeitet.")


if __name__ == "__main__":
    asyncio.run(sync())
