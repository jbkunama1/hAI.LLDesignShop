#!/usr/bin/env python3
"""
Etsy -> EverShop Importer (hAI.LLDesignShop)
Importiert listings.csv aus hAI.LLDesignEtsyScraper in EverShop via REST API.

Features:
- whiptail-Menue oder reine CLI (Args / Umgebungsvariablen)
- Idempotent: SKU = ETSY-<listing_id>, Mapping-Datei etsy_import_map.json
- Dry-Run-Modus, Fortschritts-Log, Fehler tolerant je Produkt
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DEFAULT_CSV = Path("./etsy_export/listings.csv")
DEFAULT_MAP = Path("./etsy_import_map.json")


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def has_whiptail():
    return os.path.exists("/usr/bin/whiptail")


def wt_menu(title, text, options):
    if not has_whiptail():
        return None
    cmd = ["whiptail", "--title", title, "--menu", text, "20", "70", "10"]
    for tag, item in options:
        cmd += [tag, item]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def wt_input(title, prompt, default=""):
    if not has_whiptail():
        return None
    cmd = ["whiptail", "--title", title, "--inputbox", prompt, "10", "70", default]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def slugify(text, fallback):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or fallback


class EverShopClient:
    def __init__(self, base_url, email, password):
        self.base = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.token = None

    def authenticate(self):
        r = requests.post(
            f"{self.base}/api/user/tokens",
            json={"email": self.email, "password": self.password},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        self.token = data.get("accessToken")
        if not self.token:
            raise RuntimeError("Kein accessToken in der Antwort")
        log("EverShop-Authentifizierung erfolgreich")

    def _headers(self):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def create_product(self, payload):
        r = requests.post(f"{self.base}/api/products", json=payload,
                          headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("data", {})

    def update_product(self, uuid, payload):
        r = requests.patch(f"{self.base}/api/products/{uuid}", json=payload,
                           headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("data", {})


def parse_args():
    p = argparse.ArgumentParser(
        description="Etsy CSV -> EverShop Importer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiel (CLI):
  python3 import_etsy_csv.py \\
    --csv ./etsy_export/listings.csv \\
    --evershop-url https://shop.example.com \\
    --email admin@example.com --password geheim \\
    --dry-run

Umgebungsvariablen:
  ETSY_CSV, EVERSHOP_URL, EVERSHOP_EMAIL, EVERSHOP_PASSWORD,
  IMPORT_MAP, IMPORT_STATUS, IMPORT_LIMIT
""")
    p.add_argument("--csv", type=Path, help="Pfad zur listings.csv")
    p.add_argument("--evershop-url", type=str, help="Basis-URL des EverShop-Shops")
    p.add_argument("--email", type=str, help="EverShop Admin E-Mail")
    p.add_argument("--password", type=str, help="EverShop Admin Passwort")
    p.add_argument("--map-file", type=Path, help="Mapping-Datei (Default: neben CSV)")
    p.add_argument("--status", type=int, choices=[0, 1], help="Produkt-Status (1=aktiv, 0=Entwurf)")
    p.add_argument("--limit", type=int, help="Max. Anzahl Produkte importieren")
    p.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts schreiben")
    p.add_argument("--no-menu", action="store_true", help="Kein whiptail-Menue")
    return p.parse_args()


def load_config(args):
    cfg = {}
    cfg["csv"] = args.csv or Path(os.getenv("ETSY_CSV", str(DEFAULT_CSV)))
    cfg["url"] = args.evershop_url or os.getenv("EVERSHOP_URL", "")
    cfg["email"] = args.email or os.getenv("EVERSHOP_EMAIL", "")
    cfg["password"] = args.password or os.getenv("EVERSHOP_PASSWORD", "")
    cfg["map_file"] = args.map_file or Path(os.getenv("IMPORT_MAP", str(cfg["csv"].parent / "etsy_import_map.json")))
    cfg["status"] = args.status if args.status is not None else int(os.getenv("IMPORT_STATUS", "1"))
    cfg["limit"] = args.limit or (int(os.getenv("IMPORT_LIMIT")) if os.getenv("IMPORT_LIMIT") else None)
    cfg["dry_run"] = args.dry_run
    return cfg


def read_csv(csv_path):
    with csv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_payload(row, status):
    listing_id = row["listing_id"].strip()
    title = row.get("title", "").strip() or f"Etsy {listing_id}"
    images = [u.strip() for u in row.get("image_urls", "").split("|") if u.strip()]
    desc = row.get("description", "").strip()
    short = desc[:250] + ("..." if len(desc) > 250 else "")
    qty = row.get("quantity", "").strip()
    payload = {
        "name": title,
        "sku": f"ETSY-{listing_id}",
        "url_key": slugify(title, f"etsy-{listing_id}"),
        "price": row.get("price", "0").strip() or "0",
        "qty": int(qty) if qty.isdigit() else 1,
        "status": status,
        "visibility": 1,
        "manage_stock": 1,
        "stock_availability": 1,
        "short_description": short,
        "description": desc,
        "meta_title": title,
        "meta_description": short,
        "meta_keywords": row.get("tags", "").replace("|", ", "),
        "images": images,
    }
    return payload, listing_id


def save_map(map_file, mapping):
    map_file.write_text(json.dumps(mapping, indent=2, ensure_ascii=False))


def run_import(cfg):
    if not cfg["csv"].exists():
        log(f"CSV nicht gefunden: {cfg['csv']}", "ERROR")
        return 1
    rows = read_csv(cfg["csv"])
    if cfg["limit"]:
        rows = rows[: cfg["limit"]]
    log(f"{len(rows)} Produkte in der CSV gefunden")

    mapping = {}
    if cfg["map_file"].exists():
        mapping = json.loads(cfg["map_file"].read_text())

    if cfg["dry_run"]:
        for row in rows:
            payload, lid = build_payload(row, cfg["status"])
            action = "UPDATE" if lid in mapping else "CREATE"
            log(f"[DRY-RUN] {action} | {payload['sku']} | {payload['name'][:50]} | {payload['price']} EUR | {len(payload['images'])} Bilder")
        log("Dry-Run beendet, nichts geschrieben")
        return 0

    client = EverShopClient(cfg["url"], cfg["email"], cfg["password"])
    try:
        client.authenticate()
    except Exception as e:
        log(f"Login fehlgeschlagen: {e}", "ERROR")
        return 1

    created = updated = failed = 0
    for i, row in enumerate(rows, 1):
        payload, lid = build_payload(row, cfg["status"])
        try:
            if lid in mapping and mapping[lid].get("uuid"):
                res = client.update_product(mapping[lid]["uuid"], payload)
                updated += 1
                action = "UPDATE"
            else:
                res = client.create_product(payload)
                created += 1
                action = "CREATE"
            mapping[lid] = {
                "uuid": res.get("uuid"),
                "sku": payload["sku"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            log(f"[{i}/{len(rows)}] {action} OK: {payload['sku']} - {payload['name'][:40]}")
            save_map(cfg["map_file"], mapping)
            time.sleep(0.5)
        except Exception as e:
            failed += 1
            log(f"[{i}/{len(rows)}] FEHLER bei {payload['sku']}: {e}", "ERROR")

    save_map(cfg["map_file"], mapping)
    log(f"Fertig: {created} erstellt, {updated} aktualisiert, {failed} Fehler")
    log(f"Mapping: {cfg['map_file']}")
    return 0 if failed == 0 else 1


def main():
    args = parse_args()

    if not args.no_menu and has_whiptail() and not args.csv:
        while True:
            choice = wt_menu("Etsy -> EverShop Importer", "Waehle eine Aktion:", [
                ("import", "Import starten"),
                ("dry", "Dry-Run (Vorschau)"),
                ("config", "Konfiguration eingeben"),
                ("quit", "Beenden"),
            ])
            if choice in (None, "quit"):
                sys.exit(0)
            if choice == "config":
                os.environ["EVERSHOP_URL"] = wt_input("Konfiguration", "EverShop URL:", os.getenv("EVERSHOP_URL", "")) or ""
                os.environ["EVERSHOP_EMAIL"] = wt_input("Konfiguration", "Admin E-Mail:", os.getenv("EVERSHOP_EMAIL", "")) or ""
                os.environ["EVERSHOP_PASSWORD"] = wt_input("Konfiguration", "Admin Passwort:", os.getenv("EVERSHOP_PASSWORD", "")) or ""
                os.environ["ETSY_CSV"] = wt_input("Konfiguration", "Pfad zur listings.csv:", os.getenv("ETSY_CSV", str(DEFAULT_CSV))) or str(DEFAULT_CSV)
                log("Konfiguration gespeichert (nur fuer diese Sitzung)")
                continue
            args.dry_run = choice == "dry"
            break

    cfg = load_config(args)
    if not cfg["dry_run"]:
        missing = [k for k in ("url", "email", "password") if not cfg[k]]
        if missing:
            log(f"Fehlende Konfiguration: {missing} (Args oder Env setzen)", "ERROR")
            sys.exit(2)
    sys.exit(run_import(cfg))


if __name__ == "__main__":
    main()
