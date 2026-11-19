#!/usr/bin/env python3
"""Scan the inference GTM cohort and export a private, offline dashboard."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.gtm_monitor import CORE, PEERS, collect, connect, export
from app.xclient import XDataClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "report"))
    parser.add_argument("--cohort", choices=("core", "peers"), default="core")
    parser.add_argument("--accounts", nargs="+", choices=PEERS, help="Override cohort for targeted collection")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--db", default="reports/gtm-monitor/monitor.sqlite3")
    parser.add_argument("--output", default="reports/gtm-monitor")
    parser.add_argument("--as-of", help="ISO UTC cutoff; defaults to now")
    args = parser.parse_args()
    if not 1 <= args.days <= 365 or not 1 <= args.max_pages <= 50:
        parser.error("days must be 1..365 and max-pages 1..50")
    now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else datetime.now(timezone.utc)
    if now.tzinfo is None:
        parser.error("--as-of must include a timezone")
    now = now.astimezone(timezone.utc)
    accounts = args.accounts or (CORE if args.cohort == "core" else PEERS)
    db = connect(args.db)
    result = None
    try:
        if args.command == "scan":
            settings = get_settings()
            if not settings.twitterapi_key:
                parser.error("Set TWITTERAPI_KEY in the environment or ignored .env")
            # Credentials must only reach the documented provider.
            if settings.twitterapi_base_url.rstrip("/") != "https://api.twitterapi.io":
                parser.error("GTM monitor requires the official https://api.twitterapi.io base URL")
            client = XDataClient(settings.twitterapi_key)
            result = collect(db, client, accounts, args.days, args.max_pages, now,
                             observed_at=datetime.now(timezone.utc))
            print(json.dumps(result, indent=2))
        export(db, args.output, accounts, args.days, now)
        print(f"Dashboard: {Path(args.output).resolve() / 'monitor.html'}")
    finally:
        db.close()
    if result and any(r["coverage"] not in ("window_reached", "source_exhausted") for r in result["results"].values()):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
