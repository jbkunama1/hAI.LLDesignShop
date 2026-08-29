# Etsy-Import nach EverShop

Importiert die Ausgabe von [hAI.LLDesignEtsyScraper](https://github.com/jbkunama1/hAI.LLDesignEtsyScraper) (`listings.csv`) als Produkte nach EverShop. Danach synchronisiert `sync_evershop.py` die Produkte wie gehabt in den Telegram-Bot.

## Datenfluss

```
Etsy Shop -> LLDesignEtsyScraper -> listings.csv + images/
         -> import_etsy_csv.py  -> EverShop (Webshop)
         -> sync_evershop.py    -> Telegram-Bot
```

## Voraussetzungen

- Laufender EverShop-Stack (dieses Repo)
- EverShop Admin-Zugang (E-Mail + Passwort)
- `listings.csv` aus dem Etsy-Exporter
- Python 3.9+, `requests`

## Verwendung

### Dry-Run (empfohlen zuerst)

```bash
python3 telegram-bot/import_etsy_csv.py \
  --csv ./etsy_export/listings.csv \
  --dry-run --no-menu
```

### Echter Import

```bash
python3 telegram-bot/import_etsy_csv.py \
  --csv ./etsy_export/listings.csv \
  --evershop-url https://shop.deine-domain.tld \
  --email admin@example.com \
  --password 'geheim' \
  --no-menu
```

### Interaktiv (whiptail)

```bash
python3 telegram-bot/import_etsy_csv.py
```

## Konfiguration (Args / Env)

| Argument | Env-Variable | Default |
|----------|--------------|---------|
| `--csv` | `ETSY_CSV` | `./etsy_export/listings.csv` |
| `--evershop-url` | `EVERSHOP_URL` | - |
| `--email` | `EVERSHOP_EMAIL` | - |
| `--password` | `EVERSHOP_PASSWORD` | - |
| `--map-file` | `IMPORT_MAP` | `etsy_import_map.json` neben CSV |
| `--status` | `IMPORT_STATUS` | `1` (aktiv) |
| `--limit` | `IMPORT_LIMIT` | alle |
| `--dry-run` | - | aus |
| `--no-menu` | - | Menue an |

## Feld-Mapping

| CSV (Etsy) | EverShop |
|-----------|----------|
| `title` | `name`, `meta_title`, `url_key` (slug) |
| `description` | `description`, gekuerzt in `short_description`/`meta_description` |
| `price` | `price` |
| `quantity` | `qty` |
| `listing_id` | `sku` = `ETSY-<listing_id>` |
| `tags` | `meta_keywords` |
| `image_urls` | `images` (URLs) |

## Idempotenz

Die Datei `etsy_import_map.json` merkt sich `listing_id -> uuid`. Ein erneuter Lauf aktualisiert (PATCH) statt dupliziert (POST). Mapping-Datei nicht loeschen, sonst entstehen Dubletten.

## Hinweise

- Vor dem ersten echten Lauf immer `--dry-run`.
- Nach dem Import `sync_evershop.py` laufen lassen, damit der Telegram-Bot die Produkte sieht.
- Passwort nie in die Kommandozeilen-History schreiben: besser Env-Variable oder whiptail-Eingabe nutzen.
