"""
hAI.LLDesignShop - Telegram Shop Bot
Shop: LauraLieDesign - handgefertigte Stoff-Schultueten
Katalog liegt lokal in SQLite, optional Abgleich mit EverShop via GraphQL (siehe sync_evershop.py).

Bedienung ueber Inline-Menues (Buttons direkt in der Nachricht), komplett auf Deutsch:
  /start        -> Begruessung + Hauptmenue (Inline-Buttons)
  /shop         -> identisch zu Button "Shop" im Hauptmenue
  /cart         -> identisch zu Button "Warenkorb" im Hauptmenue
  /checkout     -> identisch zu Button "Zur Kasse" im Warenkorb

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
from aiogram.fsm.storage.memory import MemoryStorage

from db import init_db, get_products, get_product, add_to_cart, get_cart, clear_cart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CURRENCY = os.getenv("CURRENCY", "EUR")

router = Router()

# ---------------------------------------------------------------------
# Shop-Texte fuer LauraLieDesign - siehe auch SHOP_TEXTS.md
# ---------------------------------------------------------------------
WELCOME_TEXT = (
    "Willkommen bei LauraLieDesign! \U0001F392\u2728\n\n"
    "Handgefertigte Stoff-Schultueten mit viel Liebe zum Detail - fuer den schoensten ersten "
    "Schultag. Jedes Motiv wird einzeln genaeht, ganz nach den Wuenschen eures Kindes.\n\n"
    "W\u00e4hle unten einen Punkt aus dem Men\u00fc:"
)

ABOUT_TEXT = (
    "\u2139\ufe0f <b>\u00dcber LauraLieDesign</b>\n\n"
    "Bei uns dreht sich alles um den sch\u00f6nsten ersten Schultag: handgefertigte "
    "Stoff-Schult\u00fcten (Zuckert\u00fcten) f\u00fcr kleine Schulanf\u00e4nger:innen \u2013 "
    "liebevoll gen\u00e4ht und individuell auf die W\u00fcnsche eures Kindes abgestimmt.\n\n"
    "\U0001F1E9\U0001F1EA Handgefertigt und versendet aus Deutschland."
)


# ---------------------------------------------------------------------
# Inline-Menues (Keyboards)
# ---------------------------------------------------------------------
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001F6CD\ufe0f Shop ansehen", callback_data="menu:shop")],
            [InlineKeyboardButton(text="\U0001F9FA Warenkorb", callback_data="menu:cart")],
            [InlineKeyboardButton(text="\u2139\ufe0f \u00dcber uns", callback_data="menu:about")],
        ]
    )


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u2b05\ufe0f Zur\u00fcck zum Men\u00fc", callback_data="menu:main")]
        ]
    )


def product_kb(product_id: int, price: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"\U0001F6D2 In den Warenkorb ({price} {CURRENCY})",
                callback_data=f"add:{product_id}",
            )]
        ]
    )


def cart_kb(items) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        rows.append([
            InlineKeyboardButton(text=f"\u2795", callback_data=f"inc:{item.product.id}"),
            InlineKeyboardButton(text=f"{item.product.name} ({item.quantity}x)", callback_data="noop"),
            InlineKeyboardButton(text=f"\u2796", callback_data=f"dec:{item.product.id}"),
        ])
    if items:
        rows.append([InlineKeyboardButton(text="\u2705 Zur Kasse", callback_data="menu:checkout")])
        rows.append([InlineKeyboardButton(text="\U0001F5D1\ufe0f Warenkorb leeren", callback_data="cart:clear")])
    rows.append([InlineKeyboardButton(text="\u2b05\ufe0f Zur\u00fcck zum Men\u00fc", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def checkout_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u2705 Bestellung jetzt abschicken", callback_data="checkout:confirm")],
            [InlineKeyboardButton(text="\u2b05\ufe0f Zur\u00fcck zum Warenkorb", callback_data="menu:cart")],
        ]
    )


# ---------------------------------------------------------------------
# Helper: Warenkorb-Text zusammenbauen
# ---------------------------------------------------------------------
async def render_cart_text(user_id: int) -> tuple[str, list]:
    items = await get_cart(user_id)
    if not items:
        return "Dein Warenkorb ist leer. St\u00f6bere gerne im Shop! \U0001F6CD\ufe0f", items

    lines = ["\U0001F9FA <b>Dein Warenkorb</b>\n"]
    total = 0
    for item in items:
        subtotal = item.product.price * item.quantity
        total += subtotal
        lines.append(f"{item.quantity}x {item.product.name} \u2013 {subtotal:.2f} {CURRENCY}")
    lines.append(f"\n<b>Gesamt: {total:.2f} {CURRENCY}</b>")
    return "\n".join(lines), items


# ---------------------------------------------------------------------
# /start -> Hauptmenue
# ---------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery):
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb())
    await callback.answer()


# ---------------------------------------------------------------------
# Shop-Ansicht
# ---------------------------------------------------------------------
async def send_shop(message: Message):
    products = await get_products()
    if not products:
        await message.answer(
            "Der Katalog ist aktuell leer. Bitte sp\u00e4ter erneut versuchen.",
            reply_markup=back_to_menu_kb(),
        )
        return

    for p in products:
        caption = f"<b>{p.name}</b>\n{p.description}\nPreis: {p.price} {CURRENCY}"
        kb = product_kb(p.id, p.price)
        if p.image_url:
            await message.answer_photo(photo=p.image_url, caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(caption, reply_markup=kb, parse_mode="HTML")

    await message.answer("Fertig gest\u00f6bert?", reply_markup=back_to_menu_kb())


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    await send_shop(message)


@router.callback_query(F.data == "menu:shop")
async def cb_menu_shop(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await send_shop(callback.message)


# ---------------------------------------------------------------------
# Warenkorb-Ansicht
# ---------------------------------------------------------------------
async def show_cart(message: Message, user_id: int, edit: bool = False):
    text, items = await render_cart_text(user_id)
    kb = cart_kb(items)
    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("cart"))
async def cmd_cart(message: Message):
    await show_cart(message, message.from_user.id)


@router.callback_query(F.data == "menu:cart")
async def cb_menu_cart(callback: CallbackQuery):
    await show_cart(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("add:"))
async def cb_add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    await add_to_cart(callback.from_user.id, product_id, quantity=1)
    product = await get_product(product_id)
    await callback.answer(f"{product.name} wurde hinzugef\u00fcgt \u2705")


@router.callback_query(F.data.startswith("inc:"))
async def cb_cart_increase(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    await add_to_cart(callback.from_user.id, product_id, quantity=1)
    await show_cart(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("dec:"))
async def cb_cart_decrease(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    await add_to_cart(callback.from_user.id, product_id, quantity=-1)
    await show_cart(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "cart:clear")
async def cb_cart_clear(callback: CallbackQuery):
    await clear_cart(callback.from_user.id)
    await show_cart(callback.message, callback.from_user.id, edit=True)
    await callback.answer("Warenkorb geleert \U0001F5D1\ufe0f")


# ---------------------------------------------------------------------
# Ueber uns
# ---------------------------------------------------------------------
@router.callback_query(F.data == "menu:about")
async def cb_menu_about(callback: CallbackQuery):
    await callback.message.edit_text(ABOUT_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------
# Checkout mit Bestaetigung
# ---------------------------------------------------------------------
async def show_checkout_confirm(message: Message, user_id: int, edit: bool = False):
    text, items = await render_cart_text(user_id)
    if not items:
        kb = back_to_menu_kb()
    else:
        text += "\n\nBestellung jetzt verbindlich abschicken?"
        kb = checkout_confirm_kb()

    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("checkout"))
async def cmd_checkout(message: Message):
    await show_checkout_confirm(message, message.from_user.id)


@router.callback_query(F.data == "menu:checkout")
async def cb_menu_checkout(callback: CallbackQuery):
    await show_checkout_confirm(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "checkout:confirm")
async def cb_checkout_confirm(callback: CallbackQuery):
    user_id = callback.from_user.id
    items = await get_cart(user_id)
    if not items:
        await callback.answer("Dein Warenkorb ist leer.", show_alert=True)
        return

    total = sum(item.product.price * item.quantity for item in items)
    order_summary = "\n".join(f"{item.quantity}x {item.product.name}" for item in items)

    user = callback.from_user
    admin_text = (
        f"\U0001F4E6 Neue Bestellung von @{user.username or user.id}\n\n"
        f"{order_summary}\n\nGesamt: {total:.2f} {CURRENCY}"
    )
    if ADMIN_CHAT_ID:
        await callback.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)

    await clear_cart(user_id)
    await callback.message.edit_text(
        "Danke f\u00fcr deine Bestellung! \u2705\n\n"
        "Wir melden uns in K\u00fcrze mit den Zahlungsdetails "
        "(z.B. PayPal-Link oder \u00dcberweisungsdaten).",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer("Bestellung abgeschickt \U0001F389")


# ---------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------
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
