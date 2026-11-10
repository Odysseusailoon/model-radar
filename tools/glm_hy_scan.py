"""Scan X for GLM-5.3 / GLM-5.3-Flash and Tencent Hunyuan Hy3/Hy4 chatter:
market reaction, open-source community feedback, coding comparisons.

Run:
    .venv/bin/python tools/glm_hy_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "glm-hy-tweets-2026-08-28.json"

GLM = '("GLM-5.3" OR "GLM 5.3" OR GLM5.3 OR "glm-5.3-flash")'
HY = '("Hy3" OR "Hy4" OR hunyuan)'

QUERIES = {
    "glm_general": f'{GLM} -filter:retweets',
    "glm_open": f'{GLM} (open OR weights OR huggingface OR MIT OR license OR vllm OR gguf OR quant OR local OR "open source" OR opensource) -filter:retweets',
    "glm_coding": f'{GLM} (coding OR code OR SWE OR agentic OR debug OR refactor OR "tool use" OR cursor OR cline OR "claude code" OR aider OR terminal) -filter:retweets',
    "glm_vs": f'{GLM} (deepseek OR kimi OR qwen OR hunyuan OR claude OR gpt OR gemini OR minimax OR compare OR versus OR vs OR beats OR better) -filter:retweets',
    "glm_ox": f'{GLM} ("ox alpha" OR "ox-alpha" OR oxalpha OR stealth OR openrouter) -filter:retweets',
    "hy_general": f'("hunyuan hy3" OR "hunyuan hy4" OR "tencent hy3" OR "tencent hy4" OR #hy3 OR #hy4) -filter:retweets',
    "hy_llm": f'(Hy3 OR Hy4) (tencent OR hunyuan OR MoE OR "open source" OR model OR LLM) -filter:retweets',
    "hy_open": f'{HY} (weights OR huggingface OR apache OR vllm OR gguf OR quant OR local OR sglang OR mlx) -filter:retweets',
    "hy_vs": f'(Hy3 OR Hy4) (deepseek OR glm OR kimi OR qwen OR claude OR gpt OR gemini OR minimax OR compare OR versus OR vs OR beats OR better) -filter:retweets',
    "hy_coding": f'(Hy3 OR Hy4) (coding OR code OR SWE OR agentic OR "claude code" OR cline OR cursor OR aider) -filter:retweets',
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
