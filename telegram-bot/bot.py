"""
hAI.LLDesignShop - Telegram Shop Bot
Shop: LauraLieDesign - handgefertigte Stoff-Schultueten
Katalog liegt lokal in SQLite, optional Abgleich mit EverShop via GraphQL (siehe sync_evershop.py).

Bedienung ueber Inline-Menues (Buttons direkt in der Nachricht), komplett auf Deutsch:
  /start        -> Begruessung + Hauptmenue (Inline-Buttons)
  /shop         -> identisch zu Button "Shop" im Hauptmenue
  /cart         -> identisch zu Button "Warenkorb" im Hauptmenue
  /checkout     -> identisch zu Button "Zur Kasse" im Warenkorb

Plausibilitaetspruefungen bei der Bestellung:
  - Lagerbestand wird vor dem finalen Abschicken erneut geprueft (Race-Condition-Schutz)
  - Maximalmenge pro Artikel begrenzt (siehe db.py: MAX_QTY_PER_ITEM)
  - Anti-Doppelklick-Schutz: pro Nutzer nur eine Bestellung gleichzeitig in Bearbeitung
  - Einfaches Rate-Limiting gegen Spam-Klicks (siehe RateLimitMiddleware)
  - Eindeutige Bestellnummer pro Bestellung (Format LLD-JJMMTT-XXXX)

Kontaktdaten-Flow (neu):
  - Vor dem finalen Checkout fragt der Bot Name und E-Mail ab (Pflicht) sowie
    optional eine Telefonnummer (ueberspringbar).
  - Daten werden pro Telegram-User-ID gespeichert (siehe db.py: Customer), damit
    wiederkehrende Kunden sie nur einmal eingeben muessen und beim naechsten Mal
    nur noch bestaetigen.
  - Der Kunde kann sofort durchbestellen, der Admin bekommt eine Benachrichtigung
    mit "Annehmen" / "Ablehnen" - das ist nicht zeitkritisch fuer den Kaufabschluss,
    sondern dient der nachtraeglichen Bearbeitung durch den Shop-Betreiber.

Fuer Zahlungen: Platzhalter-Flow ueber manuelle Bestaetigung (Ueberweisung/PayPal-Link).
Fuer Telegram Payments API / Stripe siehe README.md Abschnitt "Zahlungen".
"""

import asyncio
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    TelegramObject,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from db import (
    init_db,
    get_products,
    get_product,
    add_to_cart,
    get_cart,
    clear_cart,
    validate_cart_stock,
    finalize_order,
    get_customer,
    save_customer,
    set_order_status,
    InsufficientStockError,
    MAX_QTY_PER_ITEM,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CURRENCY = os.getenv("CURRENCY", "EUR")
RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "0.6"))

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = Router()


class CheckoutStates(StatesGroup):
    waiting_name = State()
    waiting_email = State()
    waiting_phone = State()
    confirm = State()


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
# Anti-Spam / Rate-Limiting Middleware
# ---------------------------------------------------------------------
class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_seconds: float = 0.6):
        self.limit_seconds = limit_seconds
        self._last_action: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            now = time.monotonic()
            last = self._last_action.get(user.id, 0)
            if now - last < self.limit_seconds:
                if isinstance(event, CallbackQuery):
                    await event.answer("Bitte einen Moment warten \u23f3", show_alert=False)
                return None
            self._last_action[user.id] = now
        return await handler(event, data)


# Anti-Doppelklick-Schutz beim Checkout: pro Nutzer nur eine Bestellung gleichzeitig
_checkout_locks: Dict[int, bool] = {}


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
            InlineKeyboardButton(text="\u2795", callback_data=f"inc:{item.product.id}"),
            InlineKeyboardButton(text=f"{item.product.name} ({item.quantity}x)", callback_data="noop"),
            InlineKeyboardButton(text="\u2796", callback_data=f"dec:{item.product.id}"),
        ])
    if items:
        rows.append([InlineKeyboardButton(text="\u2705 Zur Kasse", callback_data="menu:checkout")])
        rows.append([InlineKeyboardButton(text="\U0001F5D1\ufe0f Warenkorb leeren", callback_data="cart:clear")])
    rows.append([InlineKeyboardButton(text="\u2b05\ufe0f Zur\u00fcck zum Men\u00fc", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_phone_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u23ed\ufe0f \u00dcberspringen", callback_data="phone:skip")],
        ]
    )


def checkout_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u2705 Bestellung jetzt abschicken", callback_data="checkout:confirm")],
            [InlineKeyboardButton(text="\u270f\ufe0f Kontaktdaten \u00e4ndern", callback_data="checkout:edit_contact")],
            [InlineKeyboardButton(text="\u2b05\ufe0f Zur\u00fcck zum Warenkorb", callback_data="menu:cart")],
        ]
    )


def admin_order_kb(order_number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="\u2705 Annehmen", callback_data=f"admin:accept:{order_number}"),
                InlineKeyboardButton(text="\u274c Ablehnen", callback_data=f"admin:reject:{order_number}"),
            ]
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
    lines.append(f"\n<i>Maximal {MAX_QTY_PER_ITEM} St\u00fcck pro Artikel, je nach Lagerbestand.</i>")
    return "\n".join(lines), items


def render_contact_summary(name: str, email: str, phone) -> str:
    phone_line = phone if phone else "<i>nicht angegeben</i>"
    return (
        f"\U0001F464 <b>Deine Kontaktdaten</b>\n\n"
        f"Name: {name}\n"
        f"E-Mail: {email}\n"
        f"Telefon: {phone_line}"
    )


# ---------------------------------------------------------------------
# /start -> Hauptmenue
# ---------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
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
async def cb_menu_cart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_cart(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("add:"))
async def cb_add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Artikel nicht gefunden.", show_alert=True)
        return

    new_qty = await add_to_cart(callback.from_user.id, product_id, quantity=1)
    if new_qty == 0:
        await callback.answer("Dieser Artikel ist leider ausverkauft \U0001F625", show_alert=True)
    else:
        await callback.answer(f"{product.name} wurde hinzugef\u00fcgt \u2705 ({new_qty}x im Warenkorb)")


@router.callback_query(F.data.startswith("inc:"))
async def cb_cart_increase(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    new_qty = await add_to_cart(callback.from_user.id, product_id, quantity=1)
    await show_cart(callback.message, callback.from_user.id, edit=True)
    if new_qty >= MAX_QTY_PER_ITEM:
        await callback.answer(f"Maximal {MAX_QTY_PER_ITEM} St\u00fcck pro Artikel \u2139\ufe0f")
    else:
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
# Checkout: Start -> Lagerpruefung -> Kontaktdaten-Flow -> Bestaetigung
# ---------------------------------------------------------------------
async def start_checkout(callback_or_message, user_id: int, state: FSMContext, is_callback: bool):
    try:
        await validate_cart_stock(user_id)
    except InsufficientStockError as exc:
        text = f"Nur noch {exc.available}x '{exc.product_name}' verf\u00fcgbar. Bitte Menge anpassen."
        if is_callback:
            await callback_or_message.answer(text, show_alert=True)
            await show_cart(callback_or_message.message, user_id, edit=True)
        else:
            await callback_or_message.answer(text)
        return

    existing_customer = await get_customer(user_id)
    target_message = callback_or_message.message if is_callback else callback_or_message

    if existing_customer:
        await state.update_data(
            name=existing_customer.name,
            email=existing_customer.email,
            phone=existing_customer.phone,
        )
        await show_checkout_confirm(target_message, user_id, state, edit=is_callback)
    else:
        await state.set_state(CheckoutStates.waiting_name)
        text = "Bitte gib deinen vollst\u00e4ndigen Namen f\u00fcr die Bestellung ein:"
        if is_callback:
            await target_message.edit_text(text)
        else:
            await target_message.answer(text)

    if is_callback:
        await callback_or_message.answer()


@router.message(Command("checkout"))
async def cmd_checkout(message: Message, state: FSMContext):
    await start_checkout(message, message.from_user.id, state, is_callback=False)


@router.callback_query(F.data == "menu:checkout")
async def cb_menu_checkout(callback: CallbackQuery, state: FSMContext):
    await start_checkout(callback, callback.from_user.id, state, is_callback=True)


@router.callback_query(F.data == "checkout:edit_contact")
async def cb_edit_contact(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckoutStates.waiting_name)
    await callback.message.edit_text("Bitte gib deinen vollst\u00e4ndigen Namen ein:")
    await callback.answer()


@router.message(StateFilter(CheckoutStates.waiting_name))
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Bitte gib einen g\u00fcltigen Namen ein (mind. 2 Zeichen).")
        return
    await state.update_data(name=name)
    await state.set_state(CheckoutStates.waiting_email)
    await message.answer("Danke! Wie lautet deine E-Mail-Adresse? (f\u00fcr Bestellbest\u00e4tigung/R\u00fcckfragen)")


@router.message(StateFilter(CheckoutStates.waiting_email))
async def process_email(message: Message, state: FSMContext):
    email = message.text.strip()
    if not EMAIL_PATTERN.match(email):
        await message.answer("Das sieht nicht nach einer g\u00fcltigen E-Mail-Adresse aus. Bitte erneut eingeben:")
        return
    await state.update_data(email=email)
    await state.set_state(CheckoutStates.waiting_phone)
    await message.answer(
        "Optional: Telefonnummer f\u00fcr R\u00fcckfragen zur Bestellung "
        "(du kannst diesen Schritt auch \u00fcberspringen):",
        reply_markup=skip_phone_kb(),
    )


@router.message(StateFilter(CheckoutStates.waiting_phone))
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    await show_checkout_confirm(message, message.from_user.id, state, edit=False)


@router.callback_query(F.data == "phone:skip", StateFilter(CheckoutStates.waiting_phone))
async def skip_phone(callback: CallbackQuery, state: FSMContext):
    await state.update_data(phone=None)
    await callback.answer()
    await show_checkout_confirm(callback.message, callback.from_user.id, state, edit=True)


async def show_checkout_confirm(message: Message, user_id: int, state: FSMContext, edit: bool = False):
    await state.set_state(CheckoutStates.confirm)
    data = await state.get_data()

    cart_text, items = await render_cart_text(user_id)
    if not items:
        await state.clear()
        text = "Dein Warenkorb ist leer."
        kb = back_to_menu_kb()
    else:
        contact_text = render_contact_summary(data.get("name", "-"), data.get("email", "-"), data.get("phone"))
        text = f"{cart_text}\n\n{contact_text}\n\nBestellung jetzt verbindlich abschicken?"
        kb = checkout_confirm_kb()

    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "checkout:confirm", StateFilter(CheckoutStates.confirm))
async def cb_checkout_confirm(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if _checkout_locks.get(user_id):
        await callback.answer("Deine Bestellung wird bereits verarbeitet \u23f3", show_alert=True)
        return
    _checkout_locks[user_id] = True

    try:
        data = await state.get_data()
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone")

        if not name or not email:
            await callback.answer("Kontaktdaten unvollst\u00e4ndig. Bitte erneut starten.", show_alert=True)
            await state.clear()
            return

        await save_customer(user_id, name, email, phone)

        class _CustomerSnapshot:
            pass

        snapshot = _CustomerSnapshot()
        snapshot.name = name
        snapshot.email = email
        snapshot.phone = phone

        order = await finalize_order(user_id, snapshot)

        if order is None:
            await callback.answer(
                "Leider ist ein Artikel aus deinem Warenkorb nicht mehr in ausreichender "
                "St\u00fcckzahl verf\u00fcgbar. Bitte Warenkorb pr\u00fcfen.",
                show_alert=True,
            )
            await state.clear()
            await show_cart(callback.message, user_id, edit=True)
            return

        user = callback.from_user
        phone_line = phone if phone else "nicht angegeben"
        admin_text = (
            f"\U0001F4E6 Neue Bestellung {order['order_number']}\n"
            f"von @{user.username or user.id}\n\n"
            f"{order['summary']}\n\nGesamt: {order['total']:.2f} {CURRENCY}\n\n"
            f"\U0001F464 Name: {name}\n\U0001F4E7 E-Mail: {email}\n\U0001F4DE Telefon: {phone_line}\n\n"
            f"Status: offen \u2013 bitte annehmen oder ablehnen:"
        )
        if ADMIN_CHAT_ID:
            await callback.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_text,
                reply_markup=admin_order_kb(order["order_number"]),
            )

        await callback.message.edit_text(
            f"Danke f\u00fcr deine Bestellung! \u2705\n\n"
            f"Deine Bestellnummer: <b>{order['order_number']}</b>\n\n"
            f"Wir melden uns in K\u00fcrze mit den Zahlungsdetails "
            f"(z.B. PayPal-Link oder \u00dcberweisungsdaten). Bitte gib bei R\u00fcckfragen "
            f"die Bestellnummer an.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer("Bestellung abgeschickt \U0001F389")
        await state.clear()
    finally:
        _checkout_locks.pop(user_id, None)


# ---------------------------------------------------------------------
# Admin: Bestellung annehmen / ablehnen (nicht zeitkritisch, Kunde hat
# bereits final bestellt - dient der Nachbearbeitung durch den Shop-Betreiber)
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("admin:accept:"))
async def cb_admin_accept(callback: CallbackQuery):
    order_number = callback.data.split(":", 2)[2]
    order = await set_order_status(order_number, "angenommen")
    if not order:
        await callback.answer("Bestellung nicht gefunden.", show_alert=True)
        return
    await callback.message.edit_text(
        callback.message.text + f"\n\n\u2705 Angenommen",
    )
    await callback.answer("Bestellung angenommen \u2705")


@router.callback_query(F.data.startswith("admin:reject:"))
async def cb_admin_reject(callback: CallbackQuery):
    order_number = callback.data.split(":", 2)[2]
    order = await set_order_status(order_number, "abgelehnt")
    if not order:
        await callback.answer("Bestellung nicht gefunden.", show_alert=True)
        return
    await callback.message.edit_text(
        callback.message.text + f"\n\n\u274c Abgelehnt",
    )
    await callback.answer("Bestellung abgelehnt \u274c")


# ---------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN ist nicht gesetzt. Bitte .env pruefen.")

    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(RateLimitMiddleware(RATE_LIMIT_SECONDS))
    dp.callback_query.middleware(RateLimitMiddleware(RATE_LIMIT_SECONDS))
    dp.include_router(router)

    logger.info("Bot startet...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
