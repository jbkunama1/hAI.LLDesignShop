#!/usr/bin/env python3
"""
Admin-Menue fuer den LLDesignShop Telegram-Bot (aiogram v3).

Integration in bot.py:
    from admin_menu import register_admin_handlers
    register_admin_handlers(dp)
"""

import os
import sqlite3
from datetime import datetime
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()
DB_PATH = os.getenv("BOT_DB_PATH", "./shop.db")
PAGE_SIZE = 5

def get_admin_ids():
    ids = set()
    admin_chat = os.getenv("ADMIN_CHAT_ID")
    if admin_chat and admin_chat.strip().isdigit():
        ids.add(int(admin_chat.strip()))
    env_ids = os.getenv("ADMIN_IDS", "")
    for x in env_ids.split(","):
        if x.strip().isdigit():
            ids.add(int(x.strip()))
    return ids

def is_admin(user_id: int) -> bool:
    admin_ids = get_admin_ids()
    return not admin_ids or user_id in admin_ids

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None

def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Produkte", callback_data="adm:products:0")],
        [InlineKeyboardButton(text="🧾 Bestellungen", callback_data="adm:orders:0")],
        [InlineKeyboardButton(text="📊 Statistik", callback_data="adm:stats")],
        [InlineKeyboardButton(text="🔄 Sync starten", callback_data="adm:sync")],
        [InlineKeyboardButton(text="❌ Schliessen", callback_data="adm:close")],
    ])

def kb_back(target="adm:main"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Zurueck", callback_data=target)]
    ])

def kb_products(page, total, rows):
    buttons = []
    for r in rows:
        title = (r["name"] if "name" in r.keys() and r["name"] else r["sku"])[:28]
        price = r["price"] if "price" in r.keys() else 0.0
        buttons.append([InlineKeyboardButton(
            text=f"{title} – {price} EUR", callback_data=f"adm:prod:{r['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:products:{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:products:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="⬅️ Hauptmenue", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_product_detail(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📉 Bestand -1", callback_data=f"adm:stock:{pid}:-1"),
         InlineKeyboardButton(text="📈 Bestand +1", callback_data=f"adm:stock:{pid}:1")],
        [InlineKeyboardButton(text="🏷 Kategorie setzen", callback_data=f"adm:setcat:{pid}")],
        [InlineKeyboardButton(text="🌟 Empfehlung toggle", callback_data=f"adm:feat:{pid}")],
        [InlineKeyboardButton(text="🚫 Deaktivieren", callback_data=f"adm:toggle:{pid}")],
        [InlineKeyboardButton(text="⬅️ Produkte", callback_data="adm:products:0")],
    ])

def kb_orders(page, total, rows):
    buttons = []
    for r in rows:
        status = r["status"] if "status" in r.keys() else "offen"
        oid = r["id"] if "id" in r.keys() else r["order_number"]
        label = f"#{oid} – {status}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"adm:order:{r['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:orders:{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:orders:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="⬅️ Hauptmenue", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text == "/admin")
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Kein Zugriff.")
        return
    await message.answer(
        "🛠 *Admin-Menue*\nWaehle einen Bereich:",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )

@router.callback_query(F.data.startswith("adm:"))
async def on_callback(callback: CallbackQuery):
    q = callback
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.message.edit_text("⛔ Kein Zugriff.")
        return

    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else "main"

    if action == "main":
        await q.message.edit_text("🛠 *Admin-Menue*", parse_mode="Markdown",
                                  reply_markup=kb_main())
    elif action == "close":
        await q.message.delete()
    elif action == "products":
        await show_products(q, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "prod":
        await show_product_detail(q, int(parts[2]))
    elif action == "stock":
        await change_stock(q, int(parts[2]), int(parts[3]))
    elif action == "toggle":
        await toggle_product(q, int(parts[2]))
    elif action == "setcat":
        await prompt_set_category(q, int(parts[2]))
    elif action == "setcatval":
        await set_product_category(q, int(parts[2]), parts[3])
    elif action == "feat":
        await toggle_featured(q, int(parts[2]))
    elif action == "orders":
        await show_orders(q, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "order":
        await show_order_detail(q, int(parts[2]))
    elif action == "orderdone":
        await set_order_status(q, int(parts[2]), "erledigt")
    elif action == "stats":
        await show_stats(q)
    elif action == "sync":
        await run_sync(q)

async def show_products(q: CallbackQuery, page: int):
    conn = db()
    if not table_exists(conn, "products"):
        await q.message.edit_text("Keine Tabelle 'products' gefunden.",
                                  reply_markup=kb_back())
        conn.close()
        return
    total = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM products ORDER BY id LIMIT ? OFFSET ?",
        (PAGE_SIZE, page * PAGE_SIZE)).fetchall()
    conn.close()
    text = f"📦 *Produkte* ({total} gesamt, Seite {page+1})"
    await q.message.edit_text(text, parse_mode="Markdown",
                              reply_markup=kb_products(page, total, rows))

async def show_product_detail(q: CallbackQuery, pid: int):
    conn = db()
    r = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not r:
        await q.message.edit_text("Produkt nicht gefunden.", reply_markup=kb_back("adm:products:0"))
        return
    keys = r.keys()
    name = r['name'] if 'name' in keys and r['name'] else r['sku']
    price = r['price'] if 'price' in keys else 0.0
    qty = r['qty'] if 'qty' in keys else (r['stock'] if 'stock' in keys else 'N/A')
    text = (
        f"📦 *{name}*\n"
        f"SKU: `{r['sku']}`\n"
        f"Preis: {price} EUR\n"
        f"Bestand: {qty}\n"
    )
    await q.message.edit_text(text, parse_mode="Markdown",
                              reply_markup=kb_product_detail(pid))

async def change_stock(q: CallbackQuery, pid: int, delta: int):
    conn = db()
    if table_exists(conn, "products"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(products)")]
        col = "qty" if "qty" in cols else ("stock" if "stock" in cols else None)
        if col:
            conn.execute(f"UPDATE products SET {col}=MAX(0,{col}+?) WHERE id=?",
                         (delta, pid))
            conn.commit()
    conn.close()
    await show_product_detail(q, pid)

async def toggle_product(q: CallbackQuery, pid: int):
    conn = db()
    if table_exists(conn, "products"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(products)")]
        if "active" in cols:
            conn.execute("UPDATE products SET active = 1 - active WHERE id=?", (pid,))
            conn.commit()
    conn.close()
    await show_product_detail(q, pid)

CATEGORIES = ["Schultüte", "Stoff", "Zubehör", "Geschenk", "Sale"]

async def prompt_set_category(q: CallbackQuery, pid: int):
    buttons = []
    for cat in CATEGORIES:
        buttons.append([InlineKeyboardButton(text=f"🏷 {cat}", callback_data=f"adm:setcatval:{pid}:{cat}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Zurück", callback_data=f"adm:prod:{pid}")])
    await q.message.edit_text("🏷 Wähle eine Kategorie:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

async def set_product_category(q: CallbackQuery, pid: int, category: str):
    conn = db()
    if table_exists(conn, "products"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(products)")]
        if "category" in cols:
            conn.execute("UPDATE products SET category=? WHERE id=?", (category, pid))
            conn.commit()
    conn.close()
    await q.answer(f"Kategorie gesetzt: {category}")
    await show_product_detail(q, pid)

async def toggle_featured(q: CallbackQuery, pid: int):
    conn = db()
    if table_exists(conn, "products"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(products)")]
        if "featured" in cols:
            conn.execute("UPDATE products SET featured = 1 - featured WHERE id=?", (pid,))
            conn.commit()
            conn.close()
            await q.answer("Empfehlung aktualisiert")
            await show_product_detail(q, pid)
            return
    # Fallback: add the column if missing
    try:
        conn.execute("ALTER TABLE products ADD COLUMN featured INTEGER DEFAULT 0")
        conn.commit()
        conn.execute("UPDATE products SET featured = 1 - featured WHERE id=?", (pid,))
        conn.commit()
        await q.answer("Empfehlung aktualisiert (Spalte angelegt)")
    except Exception as e:
        await q.answer(f"Fehler: {e}")
    conn.close()
    await show_product_detail(q, pid)

async def show_orders(q: CallbackQuery, page: int):
    conn = db()
    if not table_exists(conn, "orders"):
        await q.message.edit_text("Keine Tabelle 'orders' gefunden.",
                                  reply_markup=kb_back())
        conn.close()
        return
    total = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE_SIZE, page * PAGE_SIZE)).fetchall()
    conn.close()
    await q.message.edit_text(
        f"🧾 *Bestellungen* ({total} gesamt)", parse_mode="Markdown",
        reply_markup=kb_orders(page, total, rows))

async def show_order_detail(q: CallbackQuery, oid: int):
    conn = db()
    r = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    conn.close()
    if not r:
        await q.message.edit_text("Bestellung nicht gefunden.",
                                  reply_markup=kb_back("adm:orders:0"))
        return
    lines = [f"🧾 *Bestellung #{r['id']}*"]
    for k in r.keys():
        if k != "id":
            lines.append(f"{k}: {r[k]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Als erledigt markieren",
                              callback_data=f"adm:orderdone:{oid}")],
        [InlineKeyboardButton(text="⬅️ Bestellungen", callback_data="adm:orders:0")],
    ])
    await q.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

async def set_order_status(q: CallbackQuery, oid: int, status: str):
    conn = db()
    if table_exists(conn, "orders"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(orders)")]
        if "status" in cols:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
            conn.commit()
    conn.close()
    await show_order_detail(q, oid)

async def show_stats(q: CallbackQuery):
    conn = db()
    products = orders = 0
    if table_exists(conn, "products"):
        products = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    if table_exists(conn, "orders"):
        orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    conn.close()
    text = (
        "📊 *Statistik*\n"
        f"Produkte: {products}\n"
        f"Bestellungen: {orders}\n"
        f"Stand: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await q.message.edit_text(text, parse_mode="Markdown", reply_markup=kb_back())

async def run_sync(q: CallbackQuery):
    await q.message.edit_text("🔄 Sync laeuft...", reply_markup=kb_back())
    import subprocess as sp
    try:
        r = sp.run(["python3", "sync_evershop.py"], capture_output=True,
                   text=True, timeout=120,
                   cwd=os.path.dirname(os.path.abspath(__file__)))
        out = (r.stdout or r.stderr or "kein Output")[-800:]
        await q.message.answer(f"Sync fertig:\n```\n{out}\n```",
                               parse_mode="Markdown")
    except Exception as e:
        await q.message.answer(f"Sync-Fehler: {e}")

def register_admin_handlers(dp):
    dp.include_router(router)
