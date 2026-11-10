"""Scan X for "ox alpha" stealth-model chatter: user sentiment, KOL takes,
coding-task comparisons vs deepseek v4 flash / GLM 5.3 / GPT 5.6 luna, and
free-platform availability.

Run:
    .venv/bin/python tools/ox_alpha_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "ox-alpha-tweets.json"

BASE = '("ox alpha" OR "ox-alpha" OR oxalpha OR #oxalpha)'
QUERIES = {
    "general": f'{BASE} -filter:retweets',
    "coding": f'{BASE} (coding OR code OR SWE OR agentic OR debug OR refactor OR "tool use" OR cursor OR cline OR "claude code" OR aider OR terminal) -filter:retweets',
    "vs": f'{BASE} (deepseek OR "v4 flash" OR GLM OR glm5 OR "glm 5.3" OR kimi OR "gpt 5.6" OR luna OR gemini OR claude OR compare OR versus OR vs OR beats OR better) -filter:retweets',
    "free": f'{BASE} (free OR openrouter OR windsurf OR "no cost" OR "for free" OR stealth OR available) -filter:retweets',
    "identity": f'{BASE} (stealth OR "who is" OR minimax OR moonshot OR "z.ai" OR qwen OR mystery OR anonymous) -filter:retweets',
}


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for tag, q in QUERIES.items():
        n0 = len(seen)
        try:
            for t in client.search_recent(q, max_pages=4):
                rec = seen.setdefault(t.id, {
                    "id": t.id,
                    "url": t.url or f"https://x.com/i/status/{t.id}",
                    "text": t.text,
                    "created": t.created_at.isoformat() if t.created_at else None,
                    "author": t.author.handle,
                    "author_name": t.author.name,
                    "followers": t.author.followers,
                    "likes": t.like_count,
                    "retweets": t.retweet_count,
                    "views": t.view_count,
                    "matched": [],
                })
                if tag not in rec["matched"]:
                    rec["matched"].append(tag)
        except Exception as exc:  # noqa: BLE001
            print(f"{tag}: ERROR {exc}")
        print(f"{tag}: +{len(seen) - n0} (total {len(seen)})", flush=True)

    tweets = sorted(seen.values(), key=lambda r: -(r.get("likes") or 0))
    OUT.write_text(json.dumps(tweets, ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT.name}: {len(tweets)}")
    for t in tweets[:25]:
        print(f"  ❤{t['likes']:>5} 👀{t.get('views') or 0:>8} @{t['author']:<18} {(t['text'] or '')[:110].replace(chr(10),' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
