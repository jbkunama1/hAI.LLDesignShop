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

Kontaktdaten-Flow:
  - Vor dem finalen Checkout fragt der Bot Name und E-Mail ab (Pflicht) sowie
    optional eine Telefonnummer (ueberspringbar).
  - Datenschutz: Nach der Eingabe fragt der Bot explizit, ob die Kontaktdaten fuer
    kuenftige Bestellungen gespeichert werden duerfen (DSGVO-Einwilligung).
  - Der Kunde kann sofort durchbestellen, der Admin bekommt eine Benachrichtigung
    mit "Annehmen" / "Ablehnen" - nicht zeitkritisch, dient der Nachbearbeitung.

Zahlungsdaten:
  - Nach dem Abschluss zeigt der Bot automatisch Ueberweisungsdaten UND einen
    PayPal.me-Link mit dem exakten Bestellbetrag an. Konfigurierbar ueber .env:
      BANK_HOLDER, BANK_IBAN, BANK_BIC, PAYPAL_ME_USERNAME

Logging (neu):
  - Ausfuehrliches Startup-Logging: Konfiguration, DB-Status, Telegram-API-Verbindung
    (Bot-Identitaet via get_me), Admin-Benachrichtigung beim Start.
  - Laufzeit-Logs fuer wichtige Ereignisse: eingehende Bestellungen, Admin-Annahme/
    -Ablehnung, Fehler bei Lagerbestand/Checkout.
  - Log-Level steuerbar ueber .env: LOG_LEVEL (Standard INFO), AIOGRAM_LOG_LEVEL
    (Standard WARNING, um aiogram-internes Rauschen zu reduzieren).
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
    get_products_by_category,
    get_categories,
    search_products,
    get_featured_products,
    InsufficientStockError,
    MAX_QTY_PER_ITEM,
)
from admin_menu import register_admin_handlers

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lauraliedesign-bot")
logging.getLogger("aiogram").setLevel(os.getenv("AIOGRAM_LOG_LEVEL", "WARNING"))

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CURRENCY = os.getenv("CURRENCY", "EUR")
RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "0.6"))

BANK_HOLDER = os.getenv("BANK_HOLDER", "Laura Lienhard")
BANK_IBAN = os.getenv("BANK_IBAN", "DE00 0000 0000 0000 0000 00")
BANK_BIC = os.getenv("BANK_BIC", "DUMMYDEFFXXX")
PAYPAL_ME_USERNAME = os.getenv("PAYPAL_ME_USERNAME", "LauraLieDesignDummy")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = Router()


class CheckoutStates(StatesGroup):
    waiting_name = State()
    waiting_email = State()
    waiting_phone = State()
    waiting_consent = State()
    confirm = State()


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

CONSENT_TEXT = (
    "\U0001F512 <b>Datenspeicherung</b>\n\n"
    "D\u00fcrfen wir deinen Namen, deine E-Mail-Adresse und ggf. Telefonnummer speichern, "
    "damit du sie bei deiner n\u00e4chsten Bestellung nicht erneut eingeben musst?\n\n"
    "Falls nicht, verwenden wir die Daten nur f\u00fcr diese eine Bestellung und legen "
    "sie nicht dauerhaft ab."
)


def build_payment_text(order_number: str, total: float) -> str:
    paypal_link = f"https://paypal.me/{PAYPAL_ME_USERNAME}/{total:.2f}{CURRENCY}"
    return (
        f"\U0001F4B3 <b>Zahlungsm\u00f6glichkeiten</b>\n\n"
        f"<b>Option A \u2013 \u00dcberweisung</b>\n"
        f"Kontoinhaber: {BANK_HOLDER}\n"
        f"IBAN: <code>{BANK_IBAN}</code>\n"
        f"BIC: <code>{BANK_BIC}</code>\n"
        f"Verwendungszweck: <code>{order_number}</code>\n\n"
        f"<b>Option B \u2013 PayPal</b>\n"
        f"\U0001F449 <a href=\"{paypal_link}\">{total:.2f} {CURRENCY} per PayPal senden</a>\n\n"
        f"<i>Bitte bei beiden Optionen die Bestellnummer als Verwendungszweck/Notiz angeben, "
        f"damit wir die Zahlung zuordnen k\u00f6nnen.</i>"
    )


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
                logger.debug("Rate-Limit ausgeloest fuer User %s", user.id)
                if isinstance(event, CallbackQuery):
                    await event.answer("Bitte einen Moment warten \u23f3", show_alert=False)
                return None
            self._last_action[user.id] = now
        return await handler(event, data)


_checkout_locks: Dict[int, bool] = {}


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Shop nach Kategorie", callback_data="menu:categories")],
            [InlineKeyboardButton(text="🔍 Suche", callback_data="menu:search")],
            [InlineKeyboardButton(text="🛒 Warenkorb", callback_data="menu:cart")],
            [InlineKeyboardButton(text="💬 Hilfe/Kontakt", callback_data="menu:help")],
            [InlineKeyboardButton(text="ℹ️ Über uns", callback_data="menu:about")],
        ]
    )

def featured_products_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌟 Empfehlung des Tages", callback_data="menu:featured")],
        ]
    )


def back_to_menu_kb() -> InlineKeyboardMarkup:
    # Fügt die Empfehlung unter die Zurück-Taste ein
    featured = featured_products_kb().inline_keyboard
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u2b05\ufe0f Zur\u00fcck zum Men\u00fc", callback_data="menu:main")]
        ] + featured
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


def consent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="\u2705 Ja, speichern", callback_data="consent:yes"),
                InlineKeyboardButton(text="\u274c Nein, nur diese Bestellung", callback_data="consent:no"),
            ]
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


def render_contact_summary(name: str, email: str, phone, save_consent) -> str:
    phone_line = phone if phone else "<i>nicht angegeben</i>"
    if save_consent is True:
        consent_line = "\U0001F513 Daten werden f\u00fcr n\u00e4chstes Mal gespeichert"
    elif save_consent is False:
        consent_line = "\U0001F512 Daten werden nicht gespeichert (nur diese Bestellung)"
    else:
        consent_line = ""
    return (
        f"\U0001F464 <b>Deine Kontaktdaten</b>\n\n"
        f"Name: {name}\n"
        f"E-Mail: {email}\n"
        f"Telefon: {phone_line}\n"
        f"{consent_line}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    logger.info("Neuer /start von User %s (@%s)", message.from_user.id, message.from_user.username)
    await state.clear()
    kb = main_menu_kb()
    # Werbung / Empfehlungen im Startmenue
    featured = await get_featured_products(1)
    if featured:
        f = featured[0]
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🌟 Tipp: {f.name} ({f.price:.2f} {CURRENCY})", callback_data=f"menu:featured")])
    await message.answer(WELCOME_TEXT, reply_markup=kb)


@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = main_menu_kb()
    # Werbung / Empfehlungen im Startmenue
    featured = await get_featured_products(1)
    if featured:
        f = featured[0]
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🌟 Tipp: {f.name} ({f.price:.2f} {CURRENCY})", callback_data=f"menu:featured")])
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=kb)
    await callback.answer()


async def send_shop(message: Message):
    products = await get_products()
    if not products:
        logger.warning("Katalog ist leer - keine Produkte mit stock > 0 vorhanden.")
        await message.answer(
            "Der Katalog ist aktuell leer. Bitte später erneut versuchen.",
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

    # Werbung / Empfehlungen unter den Produkten
    featured = await get_featured_products(2)
    if featured:
        ad_text = "💡 <b>Empfehlung der Woche (Werbung):</b>\n" + "\n".join([f"• {f.name} – <i>{f.price:.2f} {CURRENCY}</i>" for f in featured])
        await message.answer(ad_text, parse_mode="HTML")

    await message.answer("Fertig gestöbert?", reply_markup=back_to_menu_kb())


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    await send_shop(message)


@router.callback_query(F.data == "menu:shop")
async def cb_menu_shop(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await send_shop(callback.message)


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
        logger.warning("User %s wollte nicht existierendes Produkt %s hinzufuegen", callback.from_user.id, product_id)
        await callback.answer("Artikel nicht gefunden.", show_alert=True)
        return

    new_qty = await add_to_cart(callback.from_user.id, product_id, quantity=1)
    if new_qty == 0:
        logger.info("Produkt '%s' ausverkauft, User %s konnte nicht hinzufuegen", product.name, callback.from_user.id)
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


@router.callback_query(F.data == "menu:about")
async def cb_menu_about(callback: CallbackQuery):
    await callback.message.edit_text(ABOUT_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


async def start_checkout(callback_or_message, user_id: int, state: FSMContext, is_callback: bool):
    try:
        await validate_cart_stock(user_id)
    except InsufficientStockError as exc:
        logger.info("Checkout abgebrochen fuer User %s: Lagerbestand reicht nicht (%s, verfuegbar: %s)",
                    user_id, exc.product_name, exc.available)
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
        logger.info("Checkout gestartet fuer bekannten Kunden %s (%s)", user_id, existing_customer.email)
        await state.update_data(
            name=existing_customer.name,
            email=existing_customer.email,
            phone=existing_customer.phone,
            save_consent=True,
        )
        await show_checkout_confirm(target_message, user_id, state, edit=is_callback)
    else:
        logger.info("Checkout gestartet fuer neuen Kunden %s - frage Kontaktdaten ab", user_id)
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


async def ask_for_consent(message: Message, edit: bool, state: FSMContext):
    await state.set_state(CheckoutStates.waiting_consent)
    if edit:
        await message.edit_text(CONSENT_TEXT, reply_markup=consent_kb(), parse_mode="HTML")
    else:
        await message.answer(CONSENT_TEXT, reply_markup=consent_kb(), parse_mode="HTML")


@router.message(StateFilter(CheckoutStates.waiting_phone))
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    await ask_for_consent(message, edit=False, state=state)


@router.callback_query(F.data == "phone:skip", StateFilter(CheckoutStates.waiting_phone))
async def skip_phone(callback: CallbackQuery, state: FSMContext):
    await state.update_data(phone=None)
    await callback.answer()
    await ask_for_consent(callback.message, edit=True, state=state)


@router.callback_query(F.data == "consent:yes", StateFilter(CheckoutStates.waiting_consent))
async def consent_yes(callback: CallbackQuery, state: FSMContext):
    await state.update_data(save_consent=True)
    await callback.answer("Alles klar, wir merken uns deine Daten \U0001F513")
    await show_checkout_confirm(callback.message, callback.from_user.id, state, edit=True)


@router.callback_query(F.data == "consent:no", StateFilter(CheckoutStates.waiting_consent))
async def consent_no(callback: CallbackQuery, state: FSMContext):
    await state.update_data(save_consent=False)
    await callback.answer("Verstanden, nur f\u00fcr diese Bestellung \U0001F512")
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
        contact_text = render_contact_summary(
            data.get("name", "-"),
            data.get("email", "-"),
            data.get("phone"),
            data.get("save_consent"),
        )
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
        logger.warning("Doppelklick-Schutz ausgeloest fuer User %s", user_id)
        await callback.answer("Deine Bestellung wird bereits verarbeitet \u23f3", show_alert=True)
        return
    _checkout_locks[user_id] = True

    try:
        data = await state.get_data()
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone")
        save_consent = data.get("save_consent", False)

        if not name or not email:
            logger.error("Checkout fehlgeschlagen fuer User %s: Kontaktdaten unvollstaendig", user_id)
            await callback.answer("Kontaktdaten unvollst\u00e4ndig. Bitte erneut starten.", show_alert=True)
            await state.clear()
            return

        if save_consent:
            await save_customer(user_id, name, email, phone)
            logger.info("Kontaktdaten fuer User %s gespeichert (Consent erteilt)", user_id)

        class _CustomerSnapshot:
            pass

        snapshot = _CustomerSnapshot()
        snapshot.name = name
        snapshot.email = email
        snapshot.phone = phone

        order = await finalize_order(user_id, snapshot)

        if order is None:
            logger.warning("Bestellung fuer User %s fehlgeschlagen: Lagerbestand reichte beim Abschluss nicht mehr", user_id)
            await callback.answer(
                "Leider ist ein Artikel aus deinem Warenkorb nicht mehr in ausreichender "
                "St\u00fcckzahl verf\u00fcgbar. Bitte Warenkorb pr\u00fcfen.",
                show_alert=True,
            )
            await state.clear()
            await show_cart(callback.message, user_id, edit=True)
            return

        logger.info(
            "NEUE BESTELLUNG %s | User %s (@%s) | Summe: %.2f %s | Speichern: %s",
            order["order_number"], user_id, callback.from_user.username or "-",
            order["total"], CURRENCY, save_consent,
        )

        user = callback.from_user
        phone_line = phone if phone else "nicht angegeben"
        consent_line = "gespeichert" if save_consent else "nicht gespeichert (nur diese Bestellung)"
        admin_text = (
            f"\U0001F4E6 Neue Bestellung {order['order_number']}\n"
            f"von @{user.username or user.id}\n\n"
            f"{order['summary']}\n\nGesamt: {order['total']:.2f} {CURRENCY}\n\n"
            f"\U0001F464 Name: {name}\n\U0001F4E7 E-Mail: {email}\n\U0001F4DE Telefon: {phone_line}\n"
            f"\U0001F512 Kontaktdaten: {consent_line}\n\n"
            f"Status: offen \u2013 bitte annehmen oder ablehnen:"
        )
        if ADMIN_CHAT_ID:
            try:
                await callback.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=admin_text,
                    reply_markup=admin_order_kb(order["order_number"]),
                )
                logger.info("Admin-Benachrichtigung fuer Bestellung %s gesendet", order["order_number"])
            except Exception:
                logger.exception("FEHLER: Admin-Benachrichtigung fuer Bestellung %s fehlgeschlagen", order["order_number"])
        else:
            logger.warning("Keine ADMIN_CHAT_ID gesetzt - Bestellung %s wurde nicht gemeldet!", order["order_number"])

        payment_text = build_payment_text(order["order_number"], order["total"])

        await callback.message.edit_text(
            f"Danke f\u00fcr deine Bestellung! \u2705\n\n"
            f"Deine Bestellnummer: <b>{order['order_number']}</b>\n\n"
            f"{payment_text}",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await callback.answer("Bestellung abgeschickt \U0001F389")
        await state.clear()
    finally:
        _checkout_locks.pop(user_id, None)


@router.callback_query(F.data.startswith("admin:accept:"))
async def cb_admin_accept(callback: CallbackQuery):
    order_number = callback.data.split(":", 2)[2]
    order = await set_order_status(order_number, "angenommen")
    if not order:
        logger.warning("Admin-Annahme fehlgeschlagen: Bestellung %s nicht gefunden", order_number)
        await callback.answer("Bestellung nicht gefunden.", show_alert=True)
        return
    logger.info("Bestellung %s wurde vom Admin ANGENOMMEN", order_number)
    await callback.message.edit_text(
        callback.message.text + f"\n\n\u2705 Angenommen",
    )
    await callback.answer("Bestellung angenommen \u2705")


@router.callback_query(F.data.startswith("admin:reject:"))
async def cb_admin_reject(callback: CallbackQuery):
    order_number = callback.data.split(":", 2)[2]
    order = await set_order_status(order_number, "abgelehnt")
    if not order:
        logger.warning("Admin-Ablehnung fehlgeschlagen: Bestellung %s nicht gefunden", order_number)
        await callback.answer("Bestellung nicht gefunden.", show_alert=True)
        return
    logger.info("Bestellung %s wurde vom Admin ABGELEHNT", order_number)
    await callback.message.edit_text(
        callback.message.text + f"\n\n\u274c Abgelehnt",
    )
    await callback.answer("Bestellung abgelehnt \u274c")

# ── Neue Features: Kategorien, Suche, Empfehlungen, Hilfe ────────────

async def send_categories(message: Message):
    categories = await get_categories()
    if not categories:
        await message.answer("Keine Kategorien verfügbar.", reply_markup=back_to_menu_kb())
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📁 {cat}", callback_data=f"menu:cat:{cat}")] for cat in categories
    ] + [[InlineKeyboardButton(text="⬅️ Hauptmenü", callback_data="menu:main")]])
    await message.answer("Wähle eine Kategorie:", reply_markup=kb)

async def send_products_by_category(message: Message, category: str):
    products = await get_products_by_category(category)
    if not products:
        await message.answer(f"Keine Produkte in Kategorie '{category}'.", reply_markup=back_to_menu_kb("menu:categories"))
        return
    text = f"📁 <b>Kategorie: {category}</b>\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p.name} – {p.price:.2f} €", callback_data=f"product:{p.id}")] for p in products
    ] + [[InlineKeyboardButton(text="⬅️ Kategorien", callback_data="menu:categories")]])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def send_search_prompt(message: Message):
    await message.answer("🔍 <b>Produktsuche</b>\n\nGib einen Suchbegriff ein (Name oder Beschreibung):", reply_markup=back_to_menu_kb(), parse_mode="HTML")

@router.message(StateFilter(None))
async def handle_search(message: Message):
    # Einfache Suchlogik: wenn der User keine bekannte Befehle nutzt, als Suche behandeln
    text = message.text.strip()
    if not text.startswith("/") and len(text) > 1:
        products = await search_products(text)
        if products:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{p.name} – {p.price:.2f} €", callback_data=f"product:{p.id}")] for p in products
            ] + [[InlineKeyboardButton(text="⬅️ Hauptmenü", callback_data="menu:main")]])
            await message.answer(f"🔍 <b>Suchergebnisse für '{text}':</b>", reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer("Keine Produkte gefunden.", reply_markup=back_to_menu_kb())
        return

async def send_featured(message: Message):
    products = await get_featured_products(3)
    if not products:
        await message.answer("Keine Empfehlungen verfügbar.", reply_markup=back_to_menu_kb())
        return
    text = "🌟 <b>Unsere Empfehlungen</b>\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✨ {p.name} – {p.price:.2f} €", callback_data=f"product:{p.id}")] for p in products
    ] + [[InlineKeyboardButton(text="⬅️ Hauptmenü", callback_data="menu:main")]])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def send_help(message: Message):
    HELP_TEXT = (
        "💬 <b>Hilfe & Kontakt</b>\n\n"
        "Willkommen bei LauraLieDesign! 🧸\n\n"
        "<b>Wie bestelle ich?</b>\n"
        "1. Wähle 'Shop nach Kategorie' oder nutze die 'Suche'\n"
        "2. Lege Artikel in den Warenkorb 🛒\n"
        "3. Gehe zur Kasse und gib deine Kontaktdaten an\n"
        "4. Zahle per Überweisung oder PayPal\n\n"
        "<b>Kontakt</b>\n"
        "✉️ E-Mail: laura@laurakreativ.de\n"
        "📞 Telefon: +49 123 456789\n"
        "💬 Oder schreibe uns direkt hier im Chat – wir antworten schnell!\n\n"
        "<b>Datenschutz</b>\n"
        "Deine Daten werden nur für die Bestellabwicklung genutzt (DSGVO-konform).\n"
        "Du kannst jederzeit die Löschung beantragen."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Nachricht schreiben", callback_data="menu:contact")],
        [InlineKeyboardButton(text="⬅️ Hauptmenü", callback_data="menu:main")],
    ])
    await message.answer(HELP_TEXT, reply_markup=kb, parse_mode="HTML")

async def send_contact_prompt(message: Message):
    await message.answer("Schreibe deine Nachricht – wir melden uns zeitnah bei dir! ✍️", reply_markup=back_to_menu_kb())

@router.callback_query(F.data == "menu:categories")
async def cb_menu_categories(callback: CallbackQuery):
    await callback.answer()
    await send_categories(callback.message)

@router.callback_query(F.data.startswith("menu:cat:"))
async def cb_menu_category(callback: CallbackQuery):
    await callback.answer()
    category = callback.data.split(":", 2)[2]
    await send_products_by_category(callback.message, category)

@router.callback_query(F.data == "menu:search")
async def cb_menu_search(callback: CallbackQuery):
    await callback.answer()
    await send_search_prompt(callback.message)

@router.callback_query(F.data == "menu:featured")
async def cb_menu_featured(callback: CallbackQuery):
    await callback.answer()
    await send_featured(callback.message)

@router.callback_query(F.data == "menu:help")
async def cb_menu_help(callback: CallbackQuery):
    await callback.answer()
    await send_help(callback.message)

@router.callback_query(F.data == "menu:contact")
async def cb_menu_contact(callback: CallbackQuery):
    await callback.answer()
    await send_contact_prompt(callback.message)

# Product detail callback
@router.callback_query(F.data.startswith("product:"))
async def cb_product_detail(callback: CallbackQuery):
    await callback.answer()
    product_id = int(callback.data.split(":")[1])
    product = await get_product(product_id)
    if not product:
        await callback.message.edit_text("Produkt nicht gefunden.", reply_markup=back_to_menu_kb())
        return
    text = (
        f"📦 <b>{product.name}</b>\n"
        f"💰 Preis: {product.price:.2f} €\n"
        f"📦 Bestand: {product.stock}\n"
        f"📁 Kategorie: {product.category}\n"
        f"📝 {product.description}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ In den Warenkorb", callback_data=f"add:{product_id}")],
        [InlineKeyboardButton(text="⬅️ Zurück", callback_data="menu:main")],
    ] + featured_products_kb().inline_keyboard)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

async def main():
    logger.info("=" * 60)
    logger.info("hAI.LLDesignShop - Telegram Bot wird gestartet...")
    logger.info("=" * 60)

    if not BOT_TOKEN:
        logger.error("FEHLER: BOT_TOKEN ist nicht gesetzt. Bitte .env pruefen.")
        raise RuntimeError("BOT_TOKEN ist nicht gesetzt. Bitte .env pruefen.")

    logger.info("Konfiguration geladen:")
    logger.info("  CURRENCY=%s", CURRENCY)
    logger.info("  RATE_LIMIT_SECONDS=%s", RATE_LIMIT_SECONDS)
    logger.info("  MAX_QTY_PER_ITEM=%s", MAX_QTY_PER_ITEM)
    logger.info("  ADMIN_CHAT_ID gesetzt: %s", "ja" if ADMIN_CHAT_ID else "NEIN (keine Admin-Benachrichtigungen!)")
    logger.info("  BANK_HOLDER=%s", BANK_HOLDER)
    logger.info("  PAYPAL_ME_USERNAME=%s", PAYPAL_ME_USERNAME)

    logger.info("Initialisiere Datenbank...")
    try:
        await init_db()
        logger.info("Datenbank bereit (SQLite, Tabellen angelegt/geprueft).")
    except Exception:
        logger.exception("FEHLER bei der Datenbank-Initialisierung:")
        raise

    logger.info("Verbinde mit Telegram Bot API...")
    bot = Bot(token=BOT_TOKEN)

    try:
        me = await bot.get_me()
        logger.info("Verbindung erfolgreich!")
        logger.info("  Bot-Username: @%s", me.username)
        logger.info("  Bot-ID: %s", me.id)
        logger.info("  Bot-Name: %s", me.first_name)
        logger.info("  Kann Gruppen beitreten: %s", me.can_join_groups)
        logger.info("  Liest alle Gruppennachrichten: %s", me.can_read_all_group_messages)
    except Exception:
        logger.exception("FEHLER: Verbindung zur Telegram API fehlgeschlagen. BOT_TOKEN pruefen!")
        raise

    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text="\U0001F7E2 LauraLieDesign-Bot wurde gestartet und ist bereit.",
            )
            logger.info("Start-Benachrichtigung an Admin (Chat-ID %s) gesendet.", ADMIN_CHAT_ID)
        except Exception:
            logger.exception(
                "WARNUNG: Start-Benachrichtigung an Admin fehlgeschlagen. "
                "Ist ADMIN_CHAT_ID korrekt und hat der Bot dort schon /start bekommen?"
            )
    else:
        logger.warning("Keine ADMIN_CHAT_ID gesetzt - Bestellbenachrichtigungen gehen ins Leere.")

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(RateLimitMiddleware(RATE_LIMIT_SECONDS))
    dp.callback_query.middleware(RateLimitMiddleware(RATE_LIMIT_SECONDS))
    dp.include_router(router)
    register_admin_handlers(dp)

    logger.info("Registrierte Handler: %d Message-Handler, %d Callback-Handler",
                len(router.message.handlers), len(router.callback_query.handlers))

    logger.info("-" * 60)
    logger.info("Bot ist LIVE und wartet auf Nachrichten (Long Polling)...")
    logger.info("-" * 60)

    try:
        await dp.start_polling(bot)
    except Exception:
        logger.exception("FEHLER waehrend des Polling-Betriebs:")
        raise
    finally:
        logger.info("Bot-Polling beendet.")


if __name__ == "__main__":
    asyncio.run(main())
