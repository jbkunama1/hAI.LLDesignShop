#!/usr/bin/env python3
"""
Seed the Telegram bot's SQLite database with test products including images.
Run from the telegram-bot/ directory: python seed_test_products.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from db import init_db, async_session, Product
from sqlalchemy import select


# Test products with placeholder images (via placeholder.com / picsum.photos)
TEST_PRODUCTS = [
    # --- Etsy-Import: test-article, alle mit category='test-article' ===
    {
        "name": "Fabric School Cone Wild Cat Black Panther",
        "description": "Handmade fabric school cone with black panther / wild cat design. From LauraLieDesign on Etsy. Ships from Germany.",
        "price": 65.57,
        "stock": 1,
        "image_url": "https://i.etsystatic.com/18089526/r/il/ae649c/5697321403/il_794xN.5697321403_hhs5.jpg",
        "category": "test-article",
    },
    {
        "name": "Fabric School Cone With Dragon Design, Turquoise Beige",
        "description": "Handmade fabric school cone with dragon design in turquoise and beige. From LauraLieDesign on Etsy. Ships from Germany.",
        "price": 66.00,
        "stock": 1,
        "image_url": "https://i.etsystatic.com/18089526/r/il/f6f613/5697321541/il_794xN.5697321541_9rze.jpg",
        "category": "test-article",
    },
    {
        "name": "Fabric School Cone Spiderman",
        "description": "Black and red school cone with a spider web and spider design (Spiderman). From LauraLieDesign on Etsy. Ships from Germany.",
        "price": 66.04,
        "stock": 1,
        "image_url": "https://i.etsystatic.com/18089526/r/il/b367b5/5649206840/il_680x540.5649206840_7ebr.jpg",
        "category": "test-article",
    },
    {
        "name": "Fabric School Cone for Girls in Cat Sweaters",
        "description": "Cute handmade fabric school cone for girls with cat sweater design. From LauraLieDesign on Etsy. Ships from Germany.",
        "price": 53.00,
        "stock": 1,
        "image_url": "https://i.etsystatic.com/18089526/r/il/ae649c/5697321403/il_794xN.5697321403_hhs5.jpg",
        "category": "test-article",
    },
    {
        "name": "Fabric School Cone Ninja Beige (Test Variant)",
        "description": "Handmade fabric school cone in ninja style, beige colors. Test variant for import testing. From LauraLieDesign on Etsy.",
        "price": 53.00,
        "stock": 1,
        "image_url": "https://i.etsystatic.com/18089526/r/il/07968c/5697322511/il_794xN.5697322511_1ebq.jpg",
        "category": "test-article",
    },
    # --- Eigene Testprodukte ---
    {
        "name": "Handgefertigte Keramik-Tasse",
        "description": "Schöne handgefertigte Keramiktasse, perfekt für deinen morgendlichen Kaffee oder Tee. Jede Tasse ist ein Unikat mit individueller Glasur.",
        "price": 24.90,
        "stock": 15,
        "image_url": "https://picsum.photos/seed/mug1/600/600.jpg",
        "category": "test-article",
    },
    {
        "name": "Leinen-Schal 'Nordwind'",
        "description": "Leichter Leinen-Schal in natürlichen Erdtönen. Handgewebt, atmungsaktiv und ideal für Übergangszeiten. Maße: 180 x 45 cm.",
        "price": 48.00,
        "stock": 8,
        "image_url": "https://picsum.photos/seed/scarf1/600/600.jpg",
    },
    {
        "name": "Holz-Schneidebrett 'Eiche'",
        "description": "Robustes Schneidebrett aus massiver Eiche, geölt und lebensmittelecht. Mit Saftrille. Maße: 35 x 25 x 2 cm.",
        "price": 34.50,
        "stock": 12,
        "image_url": "https://picsum.photos/seed/cuttingboard1/600/600.jpg",
    },
    {
        "name": "Duftkerze 'Waldspaziergang'",
        "description": "Sojawachs-Kerze mit ätherischen Ölen (Zirbelkiefer, Zeder, Moos). Brenndauer ca. 45h. Handgegossen in wiederverwendbarem Glas.",
        "price": 19.90,
        "stock": 20,
        "image_url": "https://picsum.photos/seed/candle1/600/600.jpg",
            "category": "test-article",
        },
        {
            "name": "Makramee-Wandbehang",
            "description": "Boho-Wandbehang aus Baumwollgarn, handgeknüpft. Natürliche Optik, ca. 60 x 80 cm. Inkl. Holzstab zur Aufhängung.",
            "price": 38.00,
            "stock": 5,
            "image_url": "https://picsum.photos/seed/macrame1/600/600.jpg",
            "category": "test-article",
        },
        {
            "name": "Personalisiertes Notizbuch A5",
            "description": "Hardcover-Notizbuch mit 160 Seiten cremefarbenem Punktraster. Einband aus Recycling-Leder, personalisierbar mit Prägung.",
            "price": 22.00,
            "stock": 25,
            "image_url": "https://picsum.photos/seed/notebook1/600/600.jpg",
            "category": "test-article",
        },
    ]


async def seed():
    await init_db()

    async with async_session() as session:
        for prod in TEST_PRODUCTS:
            result = await session.execute(
                select(Product).where(Product.name == prod["name"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.price = prod["price"]
                existing.stock = prod["stock"]
                existing.image_url = prod["image_url"]
                existing.description = prod["description"]
                print(f"Updated: {prod['name']}")
            else:
                session.add(Product(**prod))
                print(f"Created: {prod['name']}")

        await session.commit()

    print(f"\nDone! {len(TEST_PRODUCTS)} test products seeded.")


if __name__ == "__main__":
    asyncio.run(seed())