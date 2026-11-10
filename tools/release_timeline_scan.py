"""Phase 1: build a 2026 release timeline for Kimi (Moonshot), GLM (Z.ai/Zhipu)
and OpenAI from X. Pulls official-account tweets month by month, plus a
keyword Top query per vendor per month as a safety net.

Run:
    .venv/bin/python tools/release_timeline_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "release-timeline-raw-2026.json"

ACCOUNTS = {
    "openai": ["OpenAI", "OpenAIDevs", "sama"],
    "kimi": ["Kimi_Moonshot"],
    "glm": ["Zai_org"],
}
KW = {
    "openai": '(openai OR "gpt-5" OR "gpt-6" OR "gpt 5" OR o5 OR codex) (introducing OR launch OR release OR released OR "now available" OR "rolling out")',
    "kimi": '(kimi OR moonshot) (introducing OR launch OR release OR released OR "open source" OR "open-source" OR weights OR K2 OR K3)',
    "glm": '("GLM" OR zhipu OR "z.ai" OR zai) (introducing OR launch OR release OR released OR "open source" OR "open-source" OR weights)',
}
MONTHS = [("2026-%02d-01" % m, "2026-%02d-01" % (m + 1)) for m in range(1, 9)] + [("2026-09-01", "2026-09-16")]


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def rec(t, vendor, tag):
    return {
        "id": t.id, "vendor": vendor, "tag": tag,
        "url": t.url or f"https://x.com/i/status/{t.id}",
        "text": t.text, "created": t.created_at.isoformat() if t.created_at else None,
        "author": t.author.handle, "followers": t.author.followers,
        "likes": t.like_count, "retweets": t.retweet_count, "views": t.view_count,
    }


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for since, until in MONTHS:
        win = f"since:{since} until:{until}"
        for vendor, handles in ACCOUNTS.items():
            for h in handles:
                q = f"from:{h} {win} -filter:replies"
                n0 = len(seen)
                try:
                    for t in client.search_recent(q, max_pages=3, query_type="Latest"):
                        seen.setdefault(t.id, rec(t, vendor, f"acct:{h}"))
                except Exception as exc:  # noqa: BLE001
                    print(f"{since} {h}: ERROR {exc}", flush=True)
                print(f"{since} from:{h}: +{len(seen)-n0}", flush=True)
        for vendor, kw in KW.items():
            q = f"{kw} {win} -filter:retweets"
            n0 = len(seen)
            try:
                for t in client.search_recent(q, max_pages=2, query_type="Top"):
                    r = seen.setdefault(t.id, rec(t, vendor, f"kw:{vendor}"))
            except Exception as exc:  # noqa: BLE001
                print(f"{since} kw:{vendor}: ERROR {exc}", flush=True)
            print(f"{since} kw:{vendor}: +{len(seen)-n0}", flush=True)
        OUT.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT.name}: {len(seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
