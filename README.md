<div align="center">

# 🛍️ hAI.LLDesignShop

### Dein unabhängiger Webshop – raus aus Etsy, rein ins Self-Hosting

**EverShop** 🛒 + **Telegram-Shop-Bot** 🤖 als kombinierter Docker-Compose-Stack

[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Portainer](https://img.shields.io/badge/Portainer-ready-13BEF9?style=for-the-badge&logo=portainer&logoColor=white)](https://www.portainer.io/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![EverShop](https://img.shields.io/badge/EverShop-Commerce-FF6B6B?style=for-the-badge&logo=graphql&logoColor=white)](https://evershop.io/)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Made with Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Node](https://img.shields.io/badge/Node.js-TypeScript-339933?style=flat-square&logo=node.js&logoColor=white)](https://nodejs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Bot--DB-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Status](https://img.shields.io/badge/Status-aktiv-brightgreen?style=flat-square)]()
[![Artikel](https://img.shields.io/badge/Katalog-≤50%20Artikel-orange?style=flat-square)]()

</div>

---

## 📖 Worum geht's?

`hAI.LLDesignShop` ist dein Fahrplan raus aus der Abhängigkeit von Etsy & Co. Ein
**vollwertiger, selbstgehosteter Webshop** kombiniert mit einem **schlanken Telegram-Bot**
für Direktverkauf im Chat – beides läuft als ein einziger Docker-Compose-Stack, den du
1:1 als **Portainer-Stack** importieren kannst.

Gedacht für kleine Shops mit bis zu **~50 Artikeln** – kein Overkill, keine unnötige Komplexität.

---

## 🧩 Architektur

```mermaid
graph TD
    A[("🐘 PostgreSQL<br/>evershop_db")] --> B["🛒 EverShop<br/>Port 3000 · GraphQL + Admin-UI"]
    B -->|"GraphQL Sync (optional)"| C["🤖 Telegram-Bot<br/>aiogram · SQLite"]
    C --> D(["💬 Kunden im Telegram-Chat"])
    B --> E(["🌐 Kunden im Webshop"])

    style A fill:#4169E1,color:#fff
    style B fill:#FF6B6B,color:#fff
    style C fill:#26A5E4,color:#fff
    style D fill:#2ecc71,color:#fff
    style E fill:#2ecc71,color:#fff
```

Der Telegram-Bot hat eine **eigene, leichtgewichtige SQLite-Datenbank** und läuft komplett
unabhängig von EverShop. Über `sync_evershop.py` kannst du optional den Produktkatalog aus
EverShop übernehmen – Katalogpflege an einer Stelle, Verkauf über zwei Kanäle. ✨

---

## 🚀 Schnellstart

```bash
# 1️⃣ Repository klonen
git clone https://github.com/jbkunama1/hAI.LLDesignShop.git
cd hAI.LLDesignShop

# 2️⃣ Umgebungsvariablen vorbereiten
cp .env.example .env
nano .env   # Werte anpassen, siehe Tabelle unten 👇

# 3️⃣ Stack starten
docker compose up -d

# 4️⃣ Logs checken
docker compose logs -f
```

Danach:

- 🛒 **EverShop-Setup** unter `http://<host>:3000` öffnen und Einrichtungsassistent durchlaufen
- 🤖 **Telegram-Bot** in Telegram öffnen und `/start` senden

### 🔑 Wichtige `.env`-Werte

| Variable | Beschreibung | Woher? |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token für deinen Bot | 🔗 [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ADMIN_CHAT_ID` | Deine Chat-ID für Bestellbenachrichtigungen | 🔗 [@userinfobot](https://t.me/userinfobot) |
| `POSTGRES_PASSWORD` | DB-Passwort für EverShop | selbst setzen, sicher & zufällig 🔒 |
| `SESSION_SECRET` | Session-Secret für EverShop | selbst setzen, sicher & zufällig 🔒 |
| `SHOP_CURRENCY` | Angezeigte Währung | Standard: `EUR` |

---

## 📁 Projektstruktur

```
hAI.LLDesignShop/
├── 🐳 docker-compose.yml       # Gesamtstack: EverShop + DB + Telegram-Bot
├── ⚙️  .env.example             # Vorlage für Umgebungsvariablen
├── 🚫 .gitignore
├── 📄 README.md
├── 📜 LICENSE
└── 🤖 telegram-bot/
    ├── Dockerfile
    ├── requirements.txt
    ├── bot.py                 # Katalog, Warenkorb, Checkout
    ├── db.py                  # SQLite-Datenschicht
    └── sync_evershop.py       # Katalog-Abgleich via GraphQL
```

---

## 🤖 Telegram-Bot: Funktionsumfang

| Befehl | Was passiert |
|---|---|
| `/start` | 👋 Begrüßung & Menü |
| `/shop` | 🖼️ Katalog als Inline-Buttons (Bild, Beschreibung, Preis) |
| `/cart` | 🧺 Warenkorb mit Zwischensumme |
| `/checkout` | ✅ Bestellung abschließen, Admin wird per Telegram benachrichtigt |

> 💡 **Checkout-Flow bewusst simpel gehalten:** Nach der Bestellung bekommst du als Admin
> eine Nachricht mit der Übersicht und meldest dich manuell mit den Zahlungsdetails
> (PayPal-Link, Überweisung o. Ä.) zurück. Reicht für den Start völlig – und lässt sich
> jederzeit automatisieren.

---

## 💳 Zahlungen

Für einen Etsy-Ersatz in 🇩🇪/🇪🇺 sind **PayPal** und **SEPA-Überweisung** meist am relevantesten.

| Weg | Beschreibung |
|---|---|
| 🅰️ **Telegram Payments API** | Native Zahlungsabwicklung im Bot, u. a. mit Stripe als Provider. Token via BotFather (`/mybots` → Payments), danach `send_invoice()` in `bot.py` ergänzen |
| 🅱️ **Manuelle Freigabe** *(aktueller Stand)* | Admin bestätigt Zahlungseingang manuell nach Bestellbenachrichtigung |

EverShop selbst bringt zusätzlich ein **Plugin-System** für reguläre Checkout- und
Zahlungsmodule mit → [EverShop-Dokumentation](https://evershop.io/docs) 📚

---

## 🗂️ Produkte pflegen

**Option A – nur EverShop pflegen** *(empfohlen ⭐)*

Produkte im EverShop-Admin (`http://<host>:3000/admin`) anlegen, danach synchronisieren:

```bash
docker compose exec telegram-bot python sync_evershop.py
```

Lässt sich super als **Cronjob** oder **GitHub Action** automatisieren. 🔁

**Option B – nur den Telegram-Bot nutzen**

Demo-Produkte direkt in `telegram-bot/db.py` ersetzen oder eigenes Insert-Skript schreiben.
Für ≤ 50 Artikel reicht das komplett aus, falls du erstmal nur den Bot live schalten willst. 🚀

---

## 🛣️ Roadmap / Ausbauideen

- [ ] 🌐 Eigene Domain + `cloudflared`-Tunnel vor EverShop (kein offener Port nötig)
- [ ] 💳 Telegram Payments API für automatisierte Zahlungsabwicklung
- [ ] 🔄 Bestell-Historie & Lagerbestand-Sync zwischen Bot und EverShop
- [ ] 💾 Backup-Strategie für `evershop_db_data` & `telegram_bot_data` (z. B. `pg_dump`-Cronjob)

---

## 📜 Lizenzhinweise

| Komponente | Lizenz |
|---|---|
| [EverShop](https://github.com/evershopcommerce/evershop) | GPL-3.0 |
| Telegram-Bot-Grundgerüst (dieses Repo) | MIT |
| Python-Abhängigkeiten (aiogram, SQLAlchemy, httpx) | MIT / Apache-2.0 |

---

<div align="center">

Made with ☕ & 🐳 für ein unabhängiges Shop-Setup abseits von Etsy

**[⭐ Repo](https://github.com/jbkunama1/hAI.LLDesignShop) · [📖 EverShop Docs](https://evershop.io/docs) · [🤖 BotFather](https://t.me/BotFather)**

</div>
