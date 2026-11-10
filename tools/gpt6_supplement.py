"""Supplement the GPT-6 Astra scan: Top-ranked (high-engagement) results,
official/insider accounts, and the pre-launch expectation window.

Run:
    .venv/bin/python tools/gpt6_supplement.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "gpt6-supplement-2026-09-03.json"
G6 = '("GPT-6" OR "GPT 6" OR GPT6 OR "GPT-6.1" OR Astra)'

TOP = {
    "top_general": ('("GPT-6" OR "GPT 6" OR GPT6 OR "GPT-6.1") -filter:retweets', "Top"),
    "top_astra": ('("GPT-6 Astra" OR "Astra" openai) -filter:retweets', "Top"),
    "top_bench": (f'{G6} (ARC-AGI OR SWE-bench OR "swe bench" OR GPQA OR FrontierMath OR benchmark OR "Artificial Analysis") -filter:retweets', "Top"),
    "top_vs_fable": (f'{G6} (fable OR opus OR claude OR gemini OR grok) -filter:retweets', "Top"),
    "top_price": (f'{G6} (pricing OR "$" OR "per million" OR "rate limit" OR limits OR quota) -filter:retweets', "Top"),
    "top_neg": (f'{G6} (overhyped OR disappointing OR underwhelming OR scam OR "not worth" OR nerf OR downgrade OR angry OR complain) -filter:retweets', "Top"),
    "top_safety": (f'{G6} (safety OR "system card" OR cybersecurity OR "critical" OR deception OR scheming OR oversight OR misalign) -filter:retweets', "Top"),
    "top_prelaunch": ('("GPT-6" OR GPT6) (leak OR leaked OR rumor OR soon OR expect OR "next week" OR launch) until:2026-09-03 -filter:retweets', "Top"),
    "openai_official": ('(from:OpenAI OR from:sama OR from:gdb OR from:kevinweil OR from:polynoamial OR from:OpenAIDevs) (GPT-6 OR Astra OR GPT6) -filter:retweets', "Latest"),
    "devs": (f'{G6} (from:theo OR from:swyx OR from:simonw OR from:levelsio OR from:mckaywrigley OR from:rohanpaul_ai OR from:_akhaliq OR from:kimmonismus)', "Latest"),
    "cn": ('("GPT-6" OR GPT6 OR Astra) (模型 OR 发布 OR 编程 OR 价格 OR 体验 OR 测评 OR 降智) -filter:retweets', "Top"),
}


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for tag, (q, qt) in TOP.items():
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
    for t in tweets[:40]:
        print(f"  ❤{t['likes']:>6} @{t['author']:<18} {(t['text'] or '')[:130].replace(chr(10),' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
