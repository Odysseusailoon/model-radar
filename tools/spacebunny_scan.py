"""Space Bunny Alpha stealth-model scan (2026-09-23).

`stealth/space-bunny-alpha` went live on OpenRouter 2026-09-23: free, 1M ctx,
524K max output, mandatory reasoning (low..max), text+image+video input.
Same playbook as ox-alpha (Aug 2026). Scan X for identity guesses, coding
takes, comparisons, and free-window chatter.

Run: .venv/bin/python tools/spacebunny_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUTPUT = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "spacebunny-tweets-2026-09-23.json")

SINCE = "since:2026-09-19_00:00:00_UTC"
BASE = '("space bunny alpha" OR "space-bunny-alpha" OR spacebunny OR "space bunny" OR #spacebunny OR spacebunnyalpha)'
AI = '(model OR openrouter OR stealth OR llm OR ai OR coding OR benchmark OR arena OR reasoning OR "1m context" OR free)'
QUERIES = {
    "slug":      (f'"space-bunny-alpha" {SINCE} -filter:retweets', 5),
    "spaced":    (f'"space bunny alpha" {SINCE} -filter:retweets', 5),
    "general":   (f'{BASE} {AI} {SINCE} -filter:retweets', 5),
    "coding":    (f'{BASE} (coding OR code OR SWE OR agentic OR debug OR "tool use" OR cursor OR cline OR "claude code" OR opencode OR aider OR terminal OR "three.js") {SINCE} -filter:retweets', 4),
    "identity":  (f'{BASE} (stealth OR "who is" OR minimax OR moonshot OR kimi OR "z.ai" OR zhipu OR glm OR qwen OR deepseek OR xai OR grok OR google OR gemini OR openai OR anthropic OR mystery OR anonymous OR tokenizer OR fingerprint) {SINCE} -filter:retweets', 4),
    "vs":        (f'{BASE} (vs OR versus OR compare OR beats OR better OR worse OR "ox alpha" OR sol OR fable OR "gpt-5.6" OR "gpt 5.6" OR opus OR sonnet) {SINCE} -filter:retweets', 4),
    "free":      (f'{BASE} (free OR "for free" OR "no cost" OR window OR "rate limit" OR limit OR quota OR privacy OR retain OR "data") {SINCE} -filter:retweets', 3),
    "official":  (f'(from:OpenRouterAI OR from:OpenRouter) {SINCE}', 3),
    "arena":     (f'(from:lmarena_ai OR from:arena) {SINCE}', 2),
    "cn":        (f'("space bunny" OR spacebunny OR 太空兔 OR 宇宙兔 OR 空间兔) (模型 OR openrouter OR 匿名 OR 实测 OR 免费 OR 马甲 OR 编程) {SINCE}', 4),
    "ja_ko":     (f'("space bunny" OR spacebunny OR スペースバニー) (モデル OR openrouter OR 匿名 OR 検証 OR 모델 OR 무료) {SINCE}', 2),
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
