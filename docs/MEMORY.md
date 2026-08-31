# AI Memory & Project Knowledge (hAI.LLDesignShop)

## Project Goals
- Provide an integrated handmade craft shop (LauraLieDesign) combining EverShop (Node.js/TypeScript/PostgreSQL) and a Telegram Shop Bot (Python/aiogram/SQLite).
- Support automated catalog sync from EverShop to the Telegram Bot via GraphQL.

## Architecture Decisions & Rationale
- **Decoupled Catalog**: Telegram Bot stores products locally in SQLite for instant responsiveness and zero downtime if EverShop is restarting.
- **Async Telegram Bot**: Built with `aiogram` v3 using routers and middleware (rate limiting, anti-double-click).
- **Admin Menu**: Direct in-Telegram admin interface (`admin_menu.py`) allowing product management, order inspection, status updates, and triggerable syncs.

## Conventions & Standards
- **Naming**: Kebab-case for scripts/files, snake_case for Python modules/functions, camelCase for JavaScript/TypeScript.
- **Ports & Networking**: EverShop runs on port 3000 (configurable via `.env`).
- **Secrets Management**: Never commit secrets or bot tokens. Always seed via `.env.example`.

## Open Items / Roadmap
- Expand automated testing for bot order placement flows.
- Enhance EverShop GraphQL sync resilience against transient network failures.
- Setup automated container image publishing to GHCR via GitHub Actions.
