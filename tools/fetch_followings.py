"""Fetch one account's full following list (handle, name, followers, bio, verified).

The following list is the useful half of a graph: followers are millions and
mostly noise, followings are hand-curated. Bios come back on this endpoint, so
the output is directly scoreable without a second lookup per account.

Run:
    .venv/bin/python tools/fetch_followings.py <handle> [out.json] [--max-pages N]
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
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--max-pages", type=int, default=30)
    a = ap.parse_args()

    handle = a.handle.lstrip("@")
    out = ROOT / (a.out or f"{handle.lower()}-followings.json")

    client = XDataClient(api_key=_key())
    users: list[dict] = []
    try:
        for u in client.user_followings(handle, max_pages=a.max_pages):
            users.append({
                "handle": u.handle,
                "name": u.name,
                "followers": u.followers,
                "bio": u.bio,
                "verified": u.verified,
            })
            if len(users) % 200 == 0:
                print(f"  {len(users)}", flush=True)
    except Exception as exc:  # noqa: BLE001
        # Partial data is still useful; record where it stopped.
        print(f"stopped early: {type(exc).__name__}: {exc} at {len(users)}", flush=True)

    # De-dupe defensively: cursor paging can repeat an account across pages.
    seen, uniq = set(), []
    for u in users:
        k = u["handle"].lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(u)

    out.write_text(json.dumps({"handle": handle, "count": len(uniq), "followings": uniq},
                              ensure_ascii=False, indent=1))
    print(f"{handle}: {len(uniq)} unique followings ({len(users) - len(uniq)} dupes dropped) -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
