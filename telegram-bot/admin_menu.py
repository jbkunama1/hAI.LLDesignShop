#!/usr/bin/env python3
"""
Admin-Menue fuer den LLDesignShop Telegram-Bot (python-telegram-bot v20+).

Integration in bot.py:
    from admin_menu import register_admin_handlers
    register_admin_handlers(app)   # app = Application.builder().token(...).build()

Admin-Zugriff: Umgebungsvariable ADMIN_IDS="123456,789012" (Telegram User-IDs).
"""

import os
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

DB_PATH = os.getenv("BOT_DB_PATH", "./shop.db")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
PAGE_SIZE = 5


def is_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


# ── Tastaturen ──────────────────────────────────────────────

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Produkte", callback_data="adm:products:0")],
        [InlineKeyboardButton("🧾 Bestellungen", callback_data="adm:orders:0")],
        [InlineKeyboardButton("📊 Statistik", callback_data="adm:stats")],
        [InlineKeyboardButton("🔄 Sync starten", callback_data="adm:sync")],
        [InlineKeyboardButton("❌ Schliessen", callback_data="adm:close")],
    ])


def kb_back(target="adm:main"):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Zurueck", callback_data=target)]]
    )


def kb_products(page, total, rows):
    buttons = []
    for r in rows:
        title = (r["name"] or r["sku"])[:28]
        buttons.append([InlineKeyboardButton(
            f"{title} – {r['price']} EUR", callback_data=f"adm:prod:{r['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm:products:{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm:products:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ Hauptmenue", callback_data="adm:main")])
    return InlineKeyboardMarkup(buttons)


def kb_product_detail(pid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📉 Bestand -1", callback_data=f"adm:stock:{pid}:-1"),
         InlineKeyboardButton("📈 Bestand +1", callback_data=f"adm:stock:{pid}:1")],
        [InlineKeyboardButton("🚫 Deaktivieren", callback_data=f"adm:toggle:{pid}")],
        [InlineKeyboardButton("⬅️ Produkte", callback_data="adm:products:0")],
    ])


def kb_orders(page, total, rows):
    buttons = []
    for r in rows:
        status = r["status"] if "status" in r.keys() else "offen"
        label = f"#{r['id']} – {status}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"adm:order:{r['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm:orders:{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm:orders:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ Hauptmenue", callback_data="adm:main")])
    return InlineKeyboardMarkup(buttons)


# ── Handler ─────────────────────────────────────────────────

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Kein Zugriff.")
        return
    await update.message.reply_text(
        "🛠 *Admin-Menue*\nWaehle einen Bereich:",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ Kein Zugriff.")
        return

    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else "main"

    if action == "main":
        await q.edit_message_text("🛠 *Admin-Menue*", parse_mode="Markdown",
                                  reply_markup=kb_main())
    elif action == "close":
        await q.delete_message()
    elif action == "products":
        await show_products(q, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "prod":
        await show_product_detail(q, int(parts[2]))
    elif action == "stock":
        await change_stock(q, int(parts[2]), int(parts[3]))
    elif action == "toggle":
        await toggle_product(q, int(parts[2]))
    elif action == "orders":
        await show_orders(q, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "order":
        await show_order_detail(q, int(parts[2]))
    elif action == "orderdone":
        await set_order_status(q, int(parts[2]), "erledigt")
    elif action == "stats":
        await show_stats(q)
    elif action == "sync":
        await run_sync(q, ctx)


async def show_products(q, page):
    conn = db()
    if not table_exists(conn, "products"):
        await q.edit_message_text("Keine Tabelle 'products' gefunden.",
                                  reply_markup=kb_back())
        return
    total = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM products ORDER BY id LIMIT ? OFFSET ?",
        (PAGE_SIZE, page * PAGE_SIZE)).fetchall()
    conn.close()
    text = f"📦 *Produkte* ({total} gesamt, Seite {page+1})"
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=kb_products(page, total, rows))


async def show_product_detail(q, pid):
    conn = db()
    r = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not r:
        await q.edit_message_text("Produkt nicht gefunden.", reply_markup=kb_back("adm:products:0"))
        return
    keys = r.keys()
    text = (
        f"📦 *{r['name'] if 'name' in keys else r['sku']}*\n"
        f"SKU: `{r['sku']}`\n"
        f"Preis: {r['price']} EUR\n"
        + (f"Bestand: {r['qty']}\n" if "qty" in keys else "")
    )
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=kb_product_detail(pid))


async def change_stock(q, pid, delta):
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


async def toggle_product(q, pid):
    conn = db()
    if table_exists(conn, "products"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(products)")]
        if "active" in cols:
            conn.execute("UPDATE products SET active = 1 - active WHERE id=?", (pid,))
            conn.commit()
    conn.close()
    await show_product_detail(q, pid)


async def show_orders(q, page):
    conn = db()
    if not table_exists(conn, "orders"):
        await q.edit_message_text("Keine Tabelle 'orders' gefunden.",
                                  reply_markup=kb_back())
        return
    total = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE_SIZE, page * PAGE_SIZE)).fetchall()
    conn.close()
    await q.edit_message_text(
        f"🧾 *Bestellungen* ({total} gesamt)", parse_mode="Markdown",
        reply_markup=kb_orders(page, total, rows))


async def show_order_detail(q, oid):
    conn = db()
    r = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    conn.close()
    if not r:
        await q.edit_message_text("Bestellung nicht gefunden.",
                                  reply_markup=kb_back("adm:orders:0"))
        return
    lines = [f"🧾 *Bestellung #{r['id']}*"]
    for k in r.keys():
        if k != "id":
            lines.append(f"{k}: {r[k]}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Als erledigt markieren",
                              callback_data=f"adm:orderdone:{oid}")],
        [InlineKeyboardButton("⬅️ Bestellungen", callback_data="adm:orders:0")],
    ])
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def set_order_status(q, oid, status):
    conn = db()
    if table_exists(conn, "orders"):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(orders)")]
        if "status" in cols:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
            conn.commit()
    conn.close()
    await show_order_detail(q, oid)


async def show_stats(q):
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
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb_back())


async def run_sync(q, ctx):
    await q.edit_message_text("🔄 Sync laeuft...", reply_markup=kb_back())
    import subprocess as sp
    try:
        r = sp.run(["python3", "sync_evershop.py"], capture_output=True,
                   text=True, timeout=120,
                   cwd=os.path.dirname(os.path.abspath(__file__)))
        out = (r.stdout or r.stderr or "kein Output")[-800:]
        await q.message.reply_text(f"Sync fertig:\n```\n{out}\n```",
                                   parse_mode="Markdown")
    except Exception as e:
        await q.message.reply_text(f"Sync-Fehler: {e}")


def register_admin_handlers(app):
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^adm:"))
