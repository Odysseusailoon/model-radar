"""Scan X for Genspark co-marketing intel: what Genspark ships, who endorses whom,
and the precedent model-vendor x app-layer co-marketing plays (Harvey x K3,
Cursor x Kimi, Genspark x Anthropic).

Run:
    .venv/bin/python tools/genspark_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "genspark-tweets-2026-09-06.json"

GS = '("genspark" OR "@genspark_ai" OR gensparkai)'

QUERIES = {
    # --- Genspark itself ---
    "gs_official": ('from:genspark_ai -filter:retweets', "Latest"),
    "gs_top": (f'{GS} -filter:retweets', "Top"),
    "gs_latest": (f'{GS} -filter:retweets', "Latest"),
    "gs_video": (f'{GS} (video OR veo OR sora OR kling OR hailuo OR minimax OR audio OR voice OR tts OR image OR nano OR banana) -filter:retweets', "Top"),
    "gs_models": (f'{GS} (claude OR anthropic OR gpt OR openai OR gemini OR grok OR kimi OR glm OR qwen OR deepseek OR "model") -filter:retweets', "Top"),
    "gs_agent": (f'{GS} (agent OR "super agent" OR superagent OR browser OR slides OR sheets OR "ai drive" OR workflow OR automation) -filter:retweets', "Top"),
    "gs_growth": (f'{GS} (ARR OR revenue OR users OR growth OR funding OR raise OR valuation OR million OR "series") -filter:retweets', "Top"),
    "gs_critique": (f'{GS} (wrapper OR expensive OR slow OR bug OR cancel OR refund OR disappointing OR overrated OR scam) -filter:retweets', "Top"),
    # --- founders / the endorsement channel ---
    "gs_founders": ('(from:ericjing OR from:kayzhu OR from:Genspark_AI) -filter:retweets', "Latest"),
    "gs_kay": ('("Kay Zhu" OR "@kayzhu" OR "Eric Jing" OR "@ericjing") -filter:retweets', "Top"),
    "gs_anthropic": ('(genspark) (anthropic OR claude OR "claude code" OR opus OR sonnet OR fable) -filter:retweets', "Top"),
    "anthropic_gs": ('(from:AnthropicAI OR from:claudeai) (genspark OR partner OR "built with") -filter:retweets', "Latest"),
    # --- precedent co-marketing plays we want to imitate ---
    "harvey_k3": ('(harvey OR harvey_ai OR harveyai) (kimi OR K3 OR moonshot OR partner OR "powered by") -filter:retweets', "Top"),
    "cursor_kimi": ('(cursor) (kimi OR K3 OR moonshot OR glm OR "z.ai" OR minimax) -filter:retweets', "Top"),
    "vendor_endorse": ('("powered by" OR "built on" OR "partnered with" OR "we chose") (kimi OR K3 OR moonshot OR minimax OR GLM OR "z.ai") (agent OR coding OR enterprise OR production) -filter:retweets', "Top"),
    # --- MiniMax side: what we can offer / how we are seen ---
    "mm_h3": ('(minimax OR hailuo) ("H3" OR "h3 max" OR "H3-Max") -filter:retweets', "Top"),
    "mm_m3": ('(minimax) ("M3" OR "M3.1" OR "M2.1" OR "M2") (model OR agent OR coding OR api OR open) -filter:retweets', "Top"),
    "mm_partners": ('(minimax OR hailuo) (partner OR partnership OR integration OR "powered by" OR "available on" OR api) -filter:retweets', "Top"),
    "mm_video_api": ('(hailuo OR minimax) (api OR "video api" OR developers OR platform OR pricing) -filter:retweets', "Latest"),
    # --- the competitive set Genspark could pick instead of us ---
    "gs_rivals": ('(genspark OR "manus" OR "flowith" OR perplexity) (comet OR "ai browser" OR "deep research" OR slides) -filter:retweets', "Top"),
}


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for tag, (q, qt) in QUERIES.items():
        n0 = len(seen)
        try:
            for t in client.search_recent(q, max_pages=3, query_type=qt):
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
    for t in tweets[:35]:
        print(f"  ❤{t['likes']:>5} @{t['author']:<18} {(t['text'] or '')[:120].replace(chr(10),' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
