"""Scan X for GPT-6 / GPT-6.1 (codenames Astra & Bel) chatter:
performance claims, benchmark reactions, coding/agentic feedback,
pricing & rollout complaints, and head-to-head vs Fable/Opus/Gemini/GLM.

Run:
    .venv/bin/python tools/gpt6_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "gpt6-tweets-2026-09-03.json"

G6 = '("GPT-6" OR "GPT 6" OR GPT6 OR "GPT-6.1" OR "gpt-6-thinking" OR "gpt-6-pro")'

QUERIES = {
    "general": f'{G6} -filter:retweets',
    "perf": f'{G6} (benchmark OR benchmarks OR eval OR evals OR SWE-bench OR "swe bench" OR ARC-AGI OR GPQA OR AIME OR FrontierMath OR HLE OR score OR SOTA OR "state of the art") -filter:retweets',
    "coding": f'{G6} (coding OR code OR agentic OR "tool use" OR codex OR cursor OR cline OR "claude code" OR aider OR terminal OR refactor OR debug) -filter:retweets',
    "vs": f'{G6} (claude OR opus OR fable OR gemini OR grok OR deepseek OR GLM OR kimi OR qwen OR hunyuan OR compare OR versus OR "vs" OR beats OR better OR worse) -filter:retweets',
    "price": f'{G6} (pricing OR price OR "per token" OR cost OR expensive OR cheap OR API OR "rate limit" OR limits OR quota OR credits OR subscription OR plus OR pro) -filter:retweets',
    "negative": f'{G6} (disappointing OR underwhelming OR overhyped OR hype OR regression OR nerfed OR worse OR mid OR flop OR "not impressed" OR meh OR refuse OR lazy) -filter:retweets',
    "positive": f'{G6} (insane OR incredible OR "holy" OR wow OR crazy OR "game changer" OR jump OR leap OR impressive OR "best model") -filter:retweets',
    "codename": f'("gpt-6" OR "gpt 6" OR openai) (astra OR "bel model" OR codename OR "code name") -filter:retweets',
    "rollout": f'{G6} (rollout OR "rolling out" OR launch OR launched OR available OR access OR waitlist OR router OR chatgpt OR deprecat) -filter:retweets',
    "enterprise": f'{G6} (enterprise OR production OR migrate OR migration OR "switched to" OR "moved to" OR deploy OR startup OR workflow) -filter:retweets',
    "context": f'{G6} (context OR "context window" OR 1M OR memory OR multimodal OR vision OR voice OR video OR latency OR speed OR "tokens per second") -filter:retweets',
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
    for t in tweets[:30]:
        print(f"  ❤{t['likes']:>5} 👀{t.get('views') or 0:>8} @{t['author']:<18} {(t['text'] or '')[:110].replace(chr(10),' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
