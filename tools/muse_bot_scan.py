"""Meta Muse (personal AI agent) X scan — launched 2026-09-08, runs on Muse Spark 1.3.

Run:
    .venv/bin/python tools/muse_bot_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUTPUT = ROOT / "muse-bot-tweets-2026-09-17.json"
SINCE = "since:2026-09-05_00:00:00_UTC"

QUERIES = {
    "muse_meta":      (f'("Meta Muse" OR "Muse agent" OR "Muse by Meta") {SINCE} -filter:retweets', 5),
    "muse_bot":       (f'("muse bot" OR "Muse Bot" OR musebot) {SINCE} -filter:retweets', 3),
    "muse_spark":     (f'("Muse Spark" OR MuseSpark) {SINCE} -filter:retweets', 4),
    "muse_ai_domain": (f'(muse.ai OR "muse.meta" OR "Muse Secure VM") {SINCE} -filter:retweets', 3),
    "official":       (f'(from:AIatMeta OR from:Meta OR from:alexandr_wang OR from:finkd) (muse OR agent) {SINCE}', 3),
    "agent_ctx":      (f'Muse (agent OR "personal AI" OR shopping OR booking OR whatsapp) meta {SINCE} -filter:retweets', 3),
    "pricing":        (f'Muse meta (pricing OR "$20" OR "$100" OR subscription OR free tier) {SINCE} -filter:retweets', 3),
    "privacy":        (f'Muse meta (privacy OR trust OR data OR creepy OR permission) {SINCE} -filter:retweets', 3),
    "bench":          (f'"Muse Spark" (benchmark OR arena OR elo OR index OR "artificial analysis" OR vs) {SINCE}', 3),
    "cn":             (f'(Muse OR "Muse Spark") (Meta OR 扎克伯格 OR 智能体 OR 实测 OR 发布) {SINCE} -filter:retweets', 3),
    "ja":             (f'Muse Meta (エージェント OR 発表 OR 使って) {SINCE} -filter:retweets', 2),
    "critique":       (f'Muse meta (disappointing OR flop OR "doesn\'t work" OR broken OR overhyped OR fails) {SINCE} -filter:retweets', 3),
}


def _twitter_api_key() -> str:
    for env_line in (ROOT / ".env").read_text().splitlines():
        if env_line.startswith("TWITTERAPI_KEY="):
            return env_line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_twitter_api_key())
    seen: dict[str, dict] = {}
    for tag, (query, pages) in QUERIES.items():
        before = len(seen)
        try:
            for tweet in client.search_recent(query, max_pages=pages):
                rec = seen.setdefault(tweet.id, {
                    "id": tweet.id,
                    "url": tweet.url or f"https://x.com/i/status/{tweet.id}",
                    "text": tweet.text,
                    "created": tweet.created_at.isoformat() if tweet.created_at else None,
                    "lang": tweet.lang,
                    "author": tweet.author.handle,
                    "author_name": tweet.author.name,
                    "followers": tweet.author.followers,
                    "likes": tweet.like_count,
                    "retweets": tweet.retweet_count,
                    "replies": tweet.reply_count,
                    "views": tweet.view_count,
                    "matched": [],
                })
                if tag not in rec["matched"]:
                    rec["matched"].append(tag)
        except Exception as exc:  # noqa: BLE001
            print(f"{tag}: ERROR {exc}", flush=True)
        print(f"{tag}: +{len(seen) - before}, total {len(seen)}", flush=True)
    rows = sorted(seen.values(), key=lambda r: (-(r.get("likes") or 0), r.get("created") or ""))
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"wrote {OUTPUT.name}: {len(rows)} rows")
    for row in rows[:40]:
        text = " ".join((row.get("text") or "").split())[:150]
        print(f"{row.get('likes',0):>5} @{row.get('author',''):<20} {row.get('url')} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
