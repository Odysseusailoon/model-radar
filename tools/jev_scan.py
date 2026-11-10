"""TypeSafe AI "Jev" decision-model X scan.

Jev = TypeSafe AI's ultra-fast / ultra-cheap System-1 decision model.
Founder: Diogo Almeida (@CompleteSkeptic), ex-OpenAI RLHF.

Run:
    .venv/bin/python tools/jev_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUTPUT = ROOT / "jev-tweets-2026-09-17.json"
SINCE = "since:2026-08-25_00:00:00_UTC"

QUERIES = {
    # brand / product
    "jev_typesafe":   (f'(Jev OR JEV) (TypeSafe OR typesafeai OR "type safe") {SINCE} -filter:retweets', 4),
    "typesafe_brand": (f'(typesafe OR "TypeSafe AI" OR typesafeai) {SINCE} -filter:retweets', 5),
    "jev_model":      (f'Jev (model OR API OR latency OR decision OR inference OR benchmark) {SINCE} -filter:retweets', 5),
    # official accounts + founder
    "official":       (f'(from:typesafeai OR from:CompleteSkeptic) {SINCE}', 4),
    "to_official":    (f'(@typesafeai OR @CompleteSkeptic) {SINCE} -filter:retweets', 5),
    "founder":        (f'("Diogo Almeida" OR CompleteSkeptic) {SINCE} -filter:retweets', 3),
    # rollout mechanics — the thesis under test
    "access":         (f'Jev (waitlist OR "invite" OR "early access" OR "now available" OR "generally available" OR preview OR signup OR "sign up") {SINCE} -filter:retweets', 4),
    "launch":         (f'(Jev OR typesafe) (launch OR launched OR ship OR shipped OR release OR released OR announce) {SINCE} -filter:retweets', 4),
    "pricing":        (f'Jev (price OR pricing OR cheaper OR "per million" OR cost OR free) {SINCE} -filter:retweets', 3),
    # capability claims and pushback
    "speed":          (f'Jev (fast OR faster OR ms OR "200x" OR "x faster" OR speed OR realtime OR "real time") {SINCE} -filter:retweets', 4),
    "usecase":        (f'Jev (classif OR router OR routing OR judge OR eval OR guardrail OR agent OR workflow) {SINCE} -filter:retweets', 4),
    "critique":       (f'Jev (hype OR overhyped OR "doesn\'t" OR limited OR skeptic OR wrong OR fails OR benchmark) typesafe {SINCE} -filter:retweets', 3),
    # architecture / research framing
    "arch":           (f'("looped transformer" OR "System 1" OR "confidence score" OR "non-autoregressive" OR "parallel decoding") (Jev OR typesafe) {SINCE} -filter:retweets', 3),
    # comparisons and non-EN
    "vs":             (f'Jev (vs OR versus OR compared) (GPT OR Astra OR Muse OR Gemini OR DeepSeek OR GLM OR Claude) {SINCE} -filter:retweets', 4),
    "cn":             (f'(Jev OR TypeSafe) (模型 OR 推理 OR 发布 OR 实测 OR 决策 OR 便宜) {SINCE} -filter:retweets', 3),
    "ja":             (f'(Jev OR TypeSafe) (モデル OR 高速 OR 発表 OR 使って OR 推論) {SINCE} -filter:retweets', 2),
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
