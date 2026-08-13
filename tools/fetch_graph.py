"""Fetch one account's followers + followings lists into a single graph file,
for mutual/follow lookups (e.g. the 与我关系 column in outreach reports).

Only handle/name/followers are kept -- relation checks don't need bios, and
skipping them keeps the file small enough to re-fetch casually.

Run:
    .venv/bin/python tools/fetch_graph.py <handle> [out.json] [--max-pages N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient  # noqa: E402


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set in .env")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--max-pages", type=int, default=150,
                    help="per side; 200 users/page, so 150 covers 30k")
    a = ap.parse_args()
    handle = a.handle.lstrip("@")
    out = Path(a.out) if a.out else ROOT / f"{handle.lower()}-graph.json"

    client = XDataClient(api_key=_key())
    graph: dict = {"handle": handle}
    for kind, fn in (("followings", client.user_followings),
                     ("followers", client.user_followers)):
        users = []
        try:
            for u in fn(handle, max_pages=a.max_pages):
                users.append({"handle": u.handle, "name": u.name, "followers": u.followers})
                if len(users) % 1000 == 0:
                    print(f"{kind}: {len(users)}", flush=True)
        except Exception as exc:  # noqa: BLE001  -- keep the partial list
            print(f"{kind}: stopped early with {exc} at {len(users)}")
        graph[kind] = users
        print(f"{kind}: {len(users)} total")

    out.write_text(json.dumps(graph, ensure_ascii=False))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
