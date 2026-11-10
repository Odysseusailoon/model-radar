"""union-alpha anonymous Arena model scan (2026-09-17).

Anonymous/stealth model codenames on LMArena get discussed under several
spellings; cover them all plus the usual "which lab is it" chatter.

Run: .venv/bin/python tools/union_alpha_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUTPUT = ROOT / "union-alpha-tweets-2026-09-17.json"

SINCE = "since:2026-08-20_00:00:00_UTC"
QUERIES = {
    "handle_exact":   (f'"union-alpha" {SINCE} -filter:retweets', 5),
    "underscore":     (f'"union_alpha" {SINCE} -filter:retweets', 3),
    "spaced":         (f'"union alpha" {SINCE} -filter:retweets', 3),
    "unionalpha":     (f'unionalpha {SINCE} -filter:retweets', 3),
    "arena_ctx":      (f'union-alpha (arena OR lmarena OR leaderboard OR elo OR battle) {SINCE}', 3),
    "guess_lab":      (f'union-alpha (openai OR google OR anthropic OR minimax OR deepseek OR qwen OR xai OR meta OR mistral) {SINCE}', 3),
    "cn":             (f'(union-alpha OR "union alpha") (匿名 OR 竞技场 OR 大模型 OR 实测 OR 榜单) {SINCE}', 3),
    "stealth_generic":(f'("anonymous model" OR "stealth model" OR "new anon") lmarena {SINCE} min_faves:5 -filter:retweets', 3),
    "lmarena_acct":   (f'(from:lmarena_ai OR from:arena) {SINCE}', 3),
}


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for tag, (query, pages) in QUERIES.items():
        before = len(seen)
        try:
            for t in client.search_recent(query, max_pages=pages):
                rec = seen.setdefault(t.id, {
                    "id": t.id,
                    "url": t.url or f"https://x.com/i/status/{t.id}",
                    "text": t.text,
                    "created": t.created_at.isoformat() if t.created_at else None,
                    "lang": t.lang,
                    "author": t.author.handle,
                    "author_name": t.author.name,
                    "followers": t.author.followers,
                    "likes": t.like_count,
                    "retweets": t.retweet_count,
                    "replies": t.reply_count,
                    "views": t.view_count,
                    "matched": [],
                })
                if tag not in rec["matched"]:
                    rec["matched"].append(tag)
        except Exception as exc:  # noqa: BLE001
            print(f"{tag}: ERROR {exc}", flush=True)
        print(f"{tag}: +{len(seen)-before}, total {len(seen)}", flush=True)
    rows = sorted(seen.values(), key=lambda r: (-(r.get("likes") or 0), r.get("created") or ""))
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"wrote {OUTPUT.name}: {len(rows)} rows")
    for r in rows[:80]:
        text = " ".join((r.get("text") or "").split())[:190]
        print(f"{r.get('likes',0):>5}L {r.get('views',0):>8}V @{r.get('author',''):<18} {r.get('created','')[:16]} {r.get('url')} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
