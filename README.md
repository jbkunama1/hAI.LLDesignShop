<div align="center">

# 🎨 hAI.LLDesignShop

### Dein unabhängiger Self-Hosting Webshop – die smarte Etsy-Alternative! 🚀

[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![EverShop](https://img.shields.io/badge/EverShop-1A1A1A?style=for-the-badge&logo=shopify&logoColor=green)](https://evershop.io/)
[![Telegram Bot](https://img.shields.io/badge/Telegram%20Bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=ffdd54)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

[![Security: TruffleHog](https://img.shields.io/badge/Security-TruffleHog-blueviolet?style=for-the-badge&logo=trufflehog&logoColor=white)](https://github.com/trufflesecurity/trufflehog)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-orange?style=for-the-badge)](https://www.gnu.org/licenses/gpl-3.0)
[![Status: Active](https://img.shields.io/badge/Status-Active-success?style=for-the-badge&logo=checkmarx&logoColor=white)]()

</div>

---

## 📑 Inhaltsverzeichnis

* [🌟 Über das Projekt](#-über-das-projekt)
* [✨ Features](#-features)
* [🛠️ Tech-Stack](#️-tech-stack)
* [🏗️ Architektur](#️-architektur)
* [🚀 Schnellstart & Deployment](#-schnellstart--deployment)
  * [Portainer Deployment](#portainer-deployment)
  * [Manuelles Deployment](#manuelles-deployment)
* [⚙️ Konfiguration (.env)](#️-konfiguration-env)
* [🤖 Telegram-Bot Befehle](#-telegram-bot-befehle)
* [💳 Zahlungen einrichten](#-zahlungen-einrichten)
* [🛡️ Sicherheit](#️-sicherheit)
* [📦 Backup](#-backup)
* [🌐 GitHub Pages](#-github-pages)
* [🗺️ Roadmap](#️-roadmap)
* [📄 Lizenz](#-lizenz)

---

## 🌟 Über das Projekt

Willkommen bei **hAI.LLDesignShop**! 👋
Dieses Repository bündelt ein komplettes, selbstgehostetes E-Commerce-Ökosystem, das perfekt als unabhängige **Etsy-Alternative** für kleine bis mittelgroße Shops (bis ca. 50 Artikel) funktioniert.

Es kombiniert:
- 🛍️ **EverShop** – ein performanter, moderner Webshop auf Node/TypeScript-Basis.
- 🤖 **Telegram-Shop-Bot** – ein schlanker Python-Bot, mit dem du direkt im Chat verkaufen kannst.
- 🐘 **PostgreSQL** – als robustes Datenbank-Backend.
- 📦 **Docker Compose** – für eine kinderleichte Bereitstellung.

---

## ✨ Features

- ✅ **Self-Hosted & DSGVO-konform** (Daten bleiben bei dir! 🇪🇺)
- ✅ **Dual-Channel Verkauf** (Webshop + Telegram)
- ✅ **Automatischer Katalog-Abgleich** (EverShop -> Bot)
- ✅ **Sichere Geheimnisse** über `.env` (TruffleHog scannt mit)
- ✅ **Automatische Docker Builds** via GitHub Actions (GHCR)
- ✅ **Backup-Strategien** (PostgreSQL & SQLite) vorbereitet
- ✅ **Portainer-kompatibel**

---

## 🛠️ Tech-Stack

| Komponente       | Technologie              | Zweck                          |
| :--------------- | :----------------------- | :----------------------------- |
| **Frontend**     | React (EverShop)         | Webshop-UI                     |
| **Backend API**  | GraphQL / Node.js        | Webshop API                    |
| **Bot**          | Python / aiogram         | Telegram-Bot Logik             |
| **DB (Web)**     | PostgreSQL 15            | EverShop Daten                 |
| **DB (Bot)**     | SQLite                   | Bot-Katalog & Bestellungen     |
| **Orchestration**| Docker Compose           | Container-Management           |
| **Security**     | TruffleHog               | Secret-Scanning in CI/CD       |

---

## 🏗️ Architektur

```text
                 ┌──────────────────────┐
                 │   EverShop DB    │  🐘 PostgreSQL
                 └────────┬────────┘
                          │
                 ┌─────────┬─────────┐
                 │   EverShop   │  🛍️ Port 3000, GraphQL + Admin-UI
                 └────────┬────────┘
                          │ 🔄 GraphQL (Katalog-Sync, optional)
                 ┌─────────┬─────────┐
                 │  🤖 Telegram-Bot    │  🐍 eigene SQLite-DB, aiogram
                 └──────────────────────┘
```

*Beide Services laufen im selben Docker-Netzwerk (`highfishNetwork`) und können optional synchronisiert werden.*

---

## 🚀 Schnellstart & Deployment

### Portainer Deployment
*(Empfohlen für Produktion)*
1. 🐳 Logge dich in dein **Portainer** ein.
2. ➡️ Gehe zu **Stacks** -> **Add Stack** -> **Repository**.
3. 🔗 Trage die URL ein: `https://github.com/jbkunama1/hAI.LLDesignShop`.
4. 📝 Trage deine `.env` Variablen (siehe unten) im UI ein.
5. 🚀 Klicke auf **Deploy the stack**.

### Manuelles Deployment
*(Auf deinem Server oder lokal)*
```bash
# 1. Klone das Repository
git clone https://github.com/jbkunama1/hAI.LLDesignShop.git
cd hAI.LLDesignShop

# 2. Konfiguriere die .env
cp .env.example .env
nano .env # Trage deine Token & Passwörter ein

# 3. Erstelle das externe Docker-Netzwerk
docker network create highfishNetwork

# 4. Starte den Stack
docker compose up -d
```

EverShop Admin-Setup unter `http://<host>:3000` aufrufen und Einrichtungsassistenten durchlaufen.

---

## ⚙️ Konfiguration (.env)

| Variable                 | Beschreibung                                          | Default              |
| :----------------------- | :---------------------------------------------------- | :------------------- |
| `DOCKER_NETWORK`         | Externes Docker-Netzwerk                              | `highfishNetwork`    |
| `SHOP_CURRENCY`          | Währung für den Shop                                  | `EUR`                |
| `EVERSHOP_PORT`          | Host-Port für den Webshop                             | `3000`               |
| `POSTGRES_DB`            | Name der Postgres DB                                  | `evershop`           |
| `POSTGRES_USER`          | Postgres User                                         | `evershop`           |
| `POSTGRES_PASSWORD`      | ⚠️ Sicheres Passwort!                                 | `changeme_...`       |
| `SESSION_SECRET`         | ⚠️ Zufälliger Session-Key!                            | `changeme_...`       |
| `TELEGRAM_BOT_TOKEN`     | 🤖 Token von @BotFather                               | *(muss gesetzt werden)* |
| `TELEGRAM_ADMIN_CHAT_ID` | Deine Chat-ID für Benachrichtigungen                  | *(muss gesetzt werden)* |

---

## 🤖 Telegram-Bot Befehle

| Befehl       | Beschreibung                                                |
| :----------- | :---------------------------------------------------------- |
| 🚀 `/start`  | Begrüßung und Hauptmenü                                     |
| 🛍️ `/shop`   | Katalog als Inline-Buttons (Bild, Beschreibung, Preis)     |
| 🛒 `/cart`   | Aktueller Warenkorb mit Zwischensumme                      |
| ✅ `/checkout`| Bestellung abschließen (Admin erhält Benachrichtigung)     |

---

## 💳 Zahlungen einrichten

1. **Telegram Payments API** (automatisiert) 🏦
   Erfordert einen Payment-Provider-Token von BotFather.
2. **Manuelle Freigabe** (Standard) 📩
   Admin versendet Zahlungsdetails (PayPal, SEPA) manuell nach Bestelleingang.

EverShop selbst bietet über das Plugin-System weitere Zahlungsmodule an (siehe [EverShop Docs](https://evershop.io/docs)).

---

## 🛡️ Sicherheit

Dieses Repository nutzt **TruffleHog** 🔍 in den GitHub Actions, um versehentlich committete Secrets zu erkennen.

Falls du eine Schwachstelle findest, lies bitte unsere [`SECURITY.md`](./SECURITY.md).

---

## 📦 Backup

Nutze das beiliegende Skript `backup.sh`, um regelmäßig Sicherungen von PostgreSQL und SQLite zu erstellen:

```bash
chmod +x backup.sh
./backup.sh
```
*(Idealerweise als Cronjob einrichten, z. B. täglich um 03:00 Uhr)*

---

## 🌐 GitHub Pages

Die zugehörige Projekt-Übersichtsseite findest du unter [`index.html`](./index.html). Aktiviere in deinen Repository-Einstellungen unter **Pages** -> `main` branch, um die Seite zu veröffentlichen. 🎉

---

## 🗺️ Roadmap

- [x] CI/CD mit TruffleHog Secret-Scanning
- [x] Docker-Build-Workflow für GHCR
- [ ] Cloudflare Tunnel Integration (Domain & HTTPS)
- [ ] Telegram Payments API Implementation
- [ ] Bestell-Historie & Lager-Synchronisation
- [ ] Automatischer CSV-Produkt-Import

---

## 📄 Lizenz

EverShop ist unter **GPL-3.0** lizenziert.
Der Telegram-Bot-Code in diesem Repo ist frei anpassbar. Externe Python-Pakete (aiogram, SQLAlchemy, httpx) stehen unter MIT/Apache-2.0.
