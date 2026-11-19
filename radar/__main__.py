"""python -m radar: list, plan, scan, resume, report. JSON output for agents."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from .catalog import load_catalog
from .engine import scan, safe_error
from .report import csv_export, markdown, summary
from .schema import ScanOptions, utc
from .sources import jobs_for
from .store import Store, ScanBusy


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", help="Watchlist JSON (defaults to INFERENCE_RADAR_CATALOG)")
    p.add_argument("--data-dir", help="Private snapshot directory (defaults to INFERENCE_RADAR_DATA_DIR)")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List configured entities as JSON; no requests")
    for name in ("plan", "scan"):
        sub = commands.add_parser(name, help="Print the request plan" if name == "plan" else "Collect a bounded evidence sample")
        sub.add_argument("--entities", default="", help="Comma-separated entity IDs")
        sub.add_argument("--groups", default="", help="engine,platform,neocloud,us_models")
        sub.add_argument("--sources", default="x,github,huggingface")
        sub.add_argument("--since", help="ISO date/time, inclusive; naive dates are UTC")
        sub.add_argument("--until", help="ISO date/time, exclusive; defaults to now")
        sub.add_argument("--days", type=int, default=7)
        sub.add_argument("--max-requests", type=int, default=60, help="HTTP attempt budget, including X retries")
        sub.add_argument("--max-pages", type=int, default=1, help="Per source/entity, 1–10")
        sub.add_argument("--page-size", type=int, default=50, help="GitHub/HF page size; X uses the provider default")
    resume = commands.add_parser("resume", help="Retry failed/skipped jobs from a saved run; successful/capped jobs are cached")
    resume.add_argument("run_id")
    report = commands.add_parser("report", help="Render a saved snapshot without network calls")
    report.add_argument("run_id", help="Run ID or 'latest'")
    report.add_argument("--format", choices=("markdown", "csv", "json"), default="markdown")
    report.add_argument("--output", help="Output file; otherwise stdout")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    settings = get_settings()
    store = Store(args.data_dir or settings.inference_radar_data_dir)
    try:
        catalog = load_catalog(args.catalog or settings.inference_radar_catalog)
        if args.command == "list":
            print(catalog.model_dump_json(indent=2))
            return 0
        if args.command == "report":
            recent = store.recent(1) if args.run_id == "latest" else []
            if args.run_id == "latest" and not recent:
                raise ValueError("No saved runs")
            run = recent[0] if recent else store.get(args.run_id)
            result = markdown(run) if args.format == "markdown" else csv_export(run) if args.format == "csv" else json.dumps(run, ensure_ascii=False, indent=2)
            if args.output:
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(result)
                print(json.dumps({"output": str(path)}))
            else:
                print(result)
            return 0
        split = lambda value: [v.strip() for v in value.split(",") if v.strip()]
        if args.command == "resume":
            saved = store.get(args.run_id)
            options = ScanOptions.model_validate(saved["options"])
            entities = catalog.select([e["id"] for e in saved["entities"]])
        else:
            until = utc(args.until) if args.until else datetime.now(timezone.utc).replace(microsecond=0)
            if not 1 <= args.days <= 366:
                raise ValueError("days must be between 1 and 366")
            options = ScanOptions(since=utc(args.since) if args.since else until - timedelta(days=args.days),
                                  until=until, sources=split(args.sources), max_requests=args.max_requests,
                                  max_pages=args.max_pages, page_size=args.page_size)
            entities = catalog.select(split(args.entities), split(args.groups))
        if not jobs_for(entities, options):
            raise ValueError("No configured sources for this selection")
        if args.command == "plan":
            print(json.dumps({"options": options.model_dump(mode="json"), "jobs": jobs_for(entities, options),
                              "catalog_hash": catalog.digest()}, ensure_ascii=False, indent=2))
            return 0
        run = scan(catalog, entities, options, store, x_key=settings.twitterapi_key,
                   github_token=settings.radar_github_token,
                   resume=args.run_id if args.command == "resume" else None)
        print(json.dumps(summary(run), ensure_ascii=False, indent=2))
        return 0 if run["status"] == "complete" else 2
    except (ValueError, FileNotFoundError, ScanBusy) as exc:
        # Validation errors may echo input. Never include credentials in CLI arguments.
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": safe_error(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
