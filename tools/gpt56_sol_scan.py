"""Dedicated X scan for GPT-5.6 Sol across four phases (preview, launch week,
stable period, post-Astra). Top channel + a Latest sample per phase.

Run:
    .venv/bin/python tools/gpt56_sol_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "gpt56-sol-tweets-2026-09-15.json"
SOL = '("GPT-5.6 Sol" OR "5.6 Sol" OR "gpt-5.6-sol" OR "Sol Ultra" OR (sol openai) OR (sol gpt))'
PHASES = {
    "preview": "since:2026-06-25 until:2026-07-08",
    "launch": "since:2026-07-08 until:2026-07-17",
    "stable": "since:2026-07-17 until:2026-09-03",
    "post_astra": "since:2026-09-03 until:2026-09-16",
}
GROUPS = {
    "general": ("", "Top", 3),
    "vs": ('(fable OR opus OR claude OR gemini OR grok OR "kimi k3" OR "GLM-5.3" OR deepseek OR qwen OR vs OR versus OR better OR benchmark OR arena OR "artificial analysis")', "Top", 2),
    "price": ('(price OR pricing OR cheaper OR cost OR "token efficient" OR efficiency OR "rate limit" OR limits OR fast OR ultrafast OR speed)', "Top", 2),
    "neg": ('(nerf OR nerfed OR worse OR disappoint OR slow OR broken OR deleted OR bug OR "reward hack" OR hallucinat OR refus OR overhyped OR downgrade OR regress OR lazy)', "Top", 2),
    "enterprise": ('(enterprise OR copilot OR microsoft OR "case study" OR production OR "we switched" OR "switched to" OR "moved to" OR "daily driver" OR team OR company OR customers)', "Top", 1),
    "science": ('(math OR proof OR conjecture OR science OR physics OR cyber OR cybersecurity OR "ARC-AGI" OR research)', "Top", 1),
    "cn": ('(模型 OR 编程 OR 体验 OR 测评 OR 价格 OR 降智 OR 好用 OR 对比)', "Top", 1),
    "latest": ("", "Latest", 2),
}


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for phase, win in PHASES.items():
        for tag, (extra, qt, pages) in GROUPS.items():
            q = f"{SOL} {extra} {win} -filter:retweets"
            n0 = len(seen)
            try:
                for t in client.search_recent(q, max_pages=pages, query_type=qt):
                    r = seen.setdefault(t.id, {
                        "id": t.id, "phase": phase, "tags": [],
                        "url": t.url or f"https://x.com/i/status/{t.id}",
                        "text": t.text, "created": t.created_at.isoformat() if t.created_at else None,
                        "author": t.author.handle, "followers": t.author.followers,
                        "likes": t.like_count, "retweets": t.retweet_count, "views": t.view_count, "lang": t.lang,
                    })
                    if tag not in r["tags"]:
                        r["tags"].append(tag)
            except Exception as exc:  # noqa: BLE001
                print(f"{phase}/{tag}: ERROR {exc}", flush=True)
            print(f"{phase}/{tag}: +{len(seen)-n0} (total {len(seen)})", flush=True)
        OUT.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT.name}: {len(seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
