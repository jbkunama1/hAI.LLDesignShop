# hAI.LLDesignShop

![TruffleHog](https://img.shields.io/badge/security-TruffleHog-blue)
![Docker Build](https://img.shields.io/badge/docker-automated-blue)

Kombiniertes Self-Hosting-Setup für einen unabhängigen Webshop als Etsy-Ersatz:

- **EverShop** – vollwertiger Webshop (TypeScript/Node, GraphQL-API, React-Frontend, PostgreSQL) für bis zu ca. 50 Artikel
- **Telegram-Shop-Bot** – schlanker Python/aiogram-Bot für Direktverkauf im Chat, mit optionalem Katalog-Abgleich aus EverShop

Beides läuft als Docker-Compose-Stack, direkt kompatibel mit Portainer (als Stack importieren).

## Architektur

```
                 ┌──────────────────────┐
                 │   EverShop DB    │  (PostgreSQL)
                 └────────┬────────┘
                          │
                 ┌─────────┬─────────┐
                 │     EverShop     │  Port 3000, GraphQL + Admin-UI
                 └────────┬────────┘
                          │ GraphQL (Katalog-Sync, optional)
                 ┌─────────┬─────────┐
                 │  Telegram-Bot    │  eigene SQLite-DB, aiogram
                 └──────────────────────┘
```

Der Telegram-Bot hat eine eigene, leichtgewichtige SQLite-Datenbank und funktioniert
komplett unabhängig von EverShop. Über `sync_evershop.py` kannst du optional den
Produktkatalog aus EverShop in den Bot übernehmen, damit du nur eine Quelle pflegen musst.

## Schnellstart

1. Repository klonen bzw. als Portainer-Stack aus diesem Repo einbinden.
2. `.env.example` nach `.env` kopieren und Werte anpassen:
   ```bash
   cp .env.example .env
   ```
3. Wichtige Werte in `.env` setzen:
   - `TELEGRAM_BOT_TOKEN` – von [@BotFather](https://t.me/BotFather) anfordern
   - `TELEGRAM_ADMIN_CHAT_ID` – deine Chat-ID für Bestellbenachrichtigungen (z. B. via `@userinfobot` ermitteln)
   - `POSTGRES_PASSWORD` und `SESSION_SECRET` – auf sichere, zufällige Werte ändern
4. Stack starten:
   ```bash
   docker compose up -d
   ```
5. EverShop Admin-Setup unter `http://<host>:3000` aufrufen und Einrichtungsassistenten durchlaufen.
6. Telegram-Bot in Telegram öffnen und `/start` senden.

## Verzeichnisstruktur

```
hAI.LLDesignShop/
├── docker-compose.yml       # Gesamtstack: EverShop + DB + Telegram-Bot
├── .env.example             # Vorlage für Umgebungsvariablen
├── .gitignore
├── README.md
└── telegram-bot/
    ├── Dockerfile
    ├── requirements.txt
    ├── bot.py                # Bot-Logik (Katalog, Warenkorb, Checkout)
    ├── db.py                 # SQLite-Datenschicht
    └── sync_evershop.py      # Optionaler Katalog-Abgleich via GraphQL
```

## Telegram-Bot: Funktionsumfang (Stand jetzt)

- `/start` – Begrüßung und Menü
- `/shop` – Katalog als Inline-Buttons (Bild, Beschreibung, Preis, "In den Warenkorb")
- `/cart` – Warenkorb mit Zwischensumme
- `/checkout` – schließt Bestellung ab, benachrichtigt dich als Admin per Telegram-Nachricht

Der Checkout-Flow ist bewusst einfach gehalten: Nach der Bestellung bekommst du (Admin) eine
Nachricht mit der Bestellübersicht und meldest dich manuell mit Zahlungsdetails (PayPal-Link,
Überweisung o. ä.) beim Kunden zurück. Das reicht für den Start völlig aus und lässt sich
später erweitern.

## Zahlungen

Für einen Etsy-Ersatz in Deutschland/EU sind PayPal und SEPA-Überweisung meist am relevantesten.
Für eine automatisierte Lösung bieten sich zwei Wege an:

1. **Telegram Payments API** – native Zahlungsabwicklung im Bot, unterstützt u. a. Stripe als
   Payment-Provider. Erfordert einen Payment-Provider-Token vom BotFather
   (`/mybots` → Payments). Danach lässt sich in `bot.py` ein `send_invoice`-Aufruf ergänzen.
2. **Manuelle Freigabe (aktueller Stand)** – wie oben beschrieben, Admin bestätigt Zahlungseingang
   manuell, z. B. per PayPal-Link, den man dem Kunden nach der Bestellung schickt.

EverShop selbst unterstützt zusätzlich reguläre Checkout- und Zahlungsmodule über sein
Plugin-System (siehe [EverShop-Dokumentation](https://evershop.io/docs)).

## Produkte pflegen

**Option A – nur EverShop pflegen (empfohlen):**
Produkte im EverShop-Admin unter `http://<host>:3000/admin` anlegen, dann `sync_evershop.py`
im Bot-Container ausführen, um den Telegram-Katalog zu aktualisieren:

```bash
docker compose exec telegram-bot python sync_evershop.py
```

Das lässt sich auch als Cronjob auf dem Host oder als GitHub Action periodisch automatisieren.

**Option B – nur Telegram-Bot nutzen:**
Direkt in `telegram-bot/db.py` die Demo-Produkte durch eigene ersetzen, oder ein kleines
Insert-Skript schreiben. Für bis zu 50 Artikel reicht das ohne EverShop völlig aus, falls
du erst einmal nur den Bot live schalten willst.

## Nächste Schritte / Ausbaumöglichkeiten

- Eigene Domain + `cloudflared`-Tunnel vor EverShop schalten (kein offener Port nötig)
- Telegram Payments API für automatisierte Zahlungsabwicklung integrieren
- Bestell-Historie und Lagerbestand-Synchronisation zwischen Bot und EverShop erweitern
- Backup-Strategie für `evershop_db_data` und `telegram_bot_data` Volumes einrichten
  (z. B. per `pg_dump`-Cronjob)

## Lizenzhinweise

- [EverShop](https://github.com/evershopcommerce/evershop) – GPL-3.0
- Telegram-Bot-Grundgerüst in diesem Repo – frei anpassbar, keine externen Lizenzabhängigkeiten
  außer den in `requirements.txt` gelisteten Python-Paketen (aiogram, SQLAlchemy, httpx, jeweils
  MIT/Apache-2.0 lizenziert)
