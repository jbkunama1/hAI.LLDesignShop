# Agents Interaction Guide

Welcome, AI Agent! When interacting with and modifying this repository (**hAI.LLDesignShop**), please adhere to the following guidelines:

1. **Tech Stack Integrity**:
   - EverShop runs on Node.js/TypeScript with PostgreSQL.
   - Telegram-Shop-Bot runs on Python (aiogram, SQLAlchemy) with SQLite.
2. **Configuration & Secrets**:
   - Never commit secrets, bot tokens, or database credentials. Use `.env` (seeded from `.env.example`).
3. **Workflow & Automation**:
   - CI/CD includes TruffleHog (secret scanning) and Docker builds for the bot.
4. **Code Quality**:
   - Keep modifications minimal and robust. Avoid unnecessary abstractions.
5. **AI Memory & MCP Integration**:
   - Repository memory is indexed via AnythingMCP (AnythingMCP Server: `https://haimcp.arbeitermili.eu/mcp/cms1vfcpi00042bs248msptyv`).
   - Consult `docs/MEMORY.md` for project goals, architecture decisions, and conventions.
