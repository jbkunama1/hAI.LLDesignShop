#!/usr/bin/env bash
# Simple Backup Script for hAI.LLDesignShop
# Backs up Postgres (EverShop) and SQLite (Telegram Bot)

BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Starting backup at $TIMESTAMP..."

# Backup Postgres DB (EverShop)
if docker ps --format '{{.Names}}' | grep -q "evershop_db"; then
    docker exec evershop_db pg_dump -U evershop evershop > "$BACKUP_DIR/postgres_$TIMESTAMP.sql"
    echo "PostgreSQL backup completed: postgres_$TIMESTAMP.sql"
else
    echo "PostgreSQL container (evershop_db) not running, skipping."
fi

# Backup SQLite DB (Telegram Bot)
if [ -f "telegram-bot/shop.db" ]; then
    cp "telegram-bot/shop.db" "$BACKUP_DIR/shop_$TIMESTAMP.db"
    echo "SQLite backup completed: shop_$TIMESTAMP.db"
fi

echo "Backup finished successfully."
