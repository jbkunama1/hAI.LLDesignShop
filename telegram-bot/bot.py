"""
hAI.LLDesignShop - Telegram Shop Bot
Shop: LauraLieDesign - handgefertigte Stoff-Schultueten
Katalog liegt lokal in SQLite, optional Abgleich mit EverShop via GraphQL (siehe sync_evershop.py).

Ablauf:
  /start        -> Begruessung + Hauptmenue
  /shop         -> Produktkatalog als Inline-Buttons
  /cart         -> Warenkorb anzeigen
  /checkout     -> Bestellung abschliessen, Admin wird benachrichtigt

Fuer Zahlungen: Platzhalter-Flow ueber manuelle Bestaetigung (Ueberweisung/PayPal-Link).
Fuer Telegram Payments API / Stripe siehe README.md Abschnitt "Zahlungen".
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from db import init_db, get_products, get_product, add_to_cart, get_cart, clear_cart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CURRENCY = os.getenv("CURRENCY", "EUR")

router = Router()

# Shop-Texte fuer LauraLieDesign - siehe auch SHOP_TEXTS.md fuer weitere Varianten
WELCOME_TEXT = (
    "Willkommen bei LauraLieDesign! \U0001F392\u2728\n\n"
    "Handgefertigte Stoff-Schultueten mit viel Liebe zum Detail - fuer den schoensten ersten "
    "Schultag. Jedes Motiv wird einzeln genaeht, ganz nach den Wuenschen eures Kindes.\n\n"
    "Befehle:\n"
    "/shop - Unsere Schultueten ansehen\n"
    "/cart - Warenkorb anzeigen\n"
    "/checkout - Bestellung abschliessen"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT)


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    products = await get_products()
    if not products:
        await message.answer("Der Katalog ist aktuell leer. Bitte spaeter erneut versuchen.")
        return

    for p in products:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"In den Warenkorb ({p.price} {CURRENCY})", callback_data=f"add:{p.id}")]
            ]
        )
        caption = f"<b>{p.name}</b>\n{p.description}\nPreis: {p.price} {CURRENCY}"
        if p.image_url:
            await message.answer_photo(photo=p.image_url, caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(caption, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("add:"))
async def cb_add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    await add_to_cart(callback.from_user.id, product_id)
    product = await get_product(product_id)
    await callback.answer(f"{product.name} wurde hinzugefuegt \u2705")


@router.message(Command("cart"))
async def cmd_cart(message: Message):
    items = await get_cart(message.from_user.id)
    if not items:
        await message.answer("Dein Warenkorb ist leer.")
        return

    lines = []
    total = 0
    for item in items:
        subtotal = item.product.price * item.quantity
        total += subtotal
        lines.append(f"{item.quantity}x {item.product.name} - {subtotal} {CURRENCY}")

    text = "\n".join(lines) + f"\n\nGesamt: {total} {CURRENCY}\n\nZum Abschliessen: /checkout"
    await message.answer(text)


@router.message(Command("checkout"))
async def cmd_checkout(message: Message):
    items = await get_cart(message.from_user.id)
    if not items:
        await message.answer("Dein Warenkorb ist leer.")
        return

    total = sum(item.product.price * item.quantity for item in items)
    order_summary = "\n".join(f"{item.quantity}x {item.product.name}" for item in items)

    user = message.from_user
    admin_text = (
        f"\U0001F4E6 Neue Bestellung von @{user.username or user.id}\n\n"
        f"{order_summary}\n\nGesamt: {total} {CURRENCY}"
    )
    if ADMIN_CHAT_ID:
        await message.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)

    await message.answer(
        "Danke fuer deine Bestellung! \u2705\n"
        "Wir melden uns in Kuerze mit den Zahlungsdetails "
        "(z.B. PayPal-Link oder Ueberweisungsdaten)."
    )
    await clear_cart(message.from_user.id)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN ist nicht gesetzt. Bitte .env pruefen.")

    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Bot startet...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
