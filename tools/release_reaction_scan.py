"""Phase 2: per-release community reaction on X (Top channel, release day + 6d).

Run:
    .venv/bin/python tools/release_reaction_scan.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "release-reactions-2026.json"

# (vendor, release key, date, match expression)
RELEASES = [
    ("kimi", "K2.5", "2026-01-27", '("Kimi K2.5" OR "K2.5" OR "Kimi Code")'),
    ("kimi", "K2.6", "2026-04-20", '("Kimi K2.6" OR "K2.6")'),
    ("kimi", "K2.7-Code", "2026-06-12", '("K2.7" OR "Kimi K2.7")'),
    ("kimi", "K3", "2026-07-16", '("Kimi K3" OR "K3" kimi OR moonshot K3)'),
    ("kimi", "K3-weights", "2026-07-27", '("Kimi K3" OR "K3" kimi) (weights OR "open" OR huggingface OR "tech report" OR "technical report")'),
    ("glm", "GLM-4.7-Flash", "2026-01-19", '("GLM-4.7-Flash" OR "GLM 4.7 Flash" OR "GLM-4.7")'),
    ("glm", "GLM-5", "2026-02-11", '("GLM-5" OR "GLM 5" OR GLM5) -"GLM-5.1" -"GLM-5.2" -"GLM-5.3"'),
    ("glm", "GLM-5-Turbo", "2026-03-15", '("GLM-5-Turbo" OR "GLM 5 Turbo")'),
    ("glm", "GLM-5.1", "2026-04-07", '("GLM-5.1" OR "GLM 5.1")'),
    ("glm", "GLM-5V-Turbo", "2026-04-01", '("GLM-5V" OR "GLM 5V")'),
    ("glm", "GLM-5.2", "2026-06-16", '("GLM-5.2" OR "GLM 5.2")'),
    ("glm", "GLM-5.3", "2026-08-14", '("GLM-5.3" OR "GLM 5.3") -flash'),
    ("glm", "GLM-5.3-Flash", "2026-08-26", '("GLM-5.3-Flash" OR "GLM 5.3 Flash" OR "5.3 flash")'),
    ("glm", "GLM-5.3-weights", "2026-08-28", '("GLM-5.3" OR "GLM 5.3") (weights OR "open-weight" OR "open weight" OR huggingface OR "open source")'),
    ("openai", "GPT-5.3-Codex", "2026-02-05", '("GPT-5.3-Codex" OR "5.3-Codex" OR "gpt 5.3 codex" OR "5.3 codex")'),
    ("openai", "Codex-Spark", "2026-02-12", '("Codex-Spark" OR "Codex Spark" OR spark codex)'),
    ("openai", "GPT-5.3-Instant", "2026-03-03", '("GPT-5.3 Instant" OR "5.3 instant")'),
    ("openai", "GPT-5.4", "2026-03-05", '("GPT-5.4" OR "GPT 5.4" OR gpt5.4) -mini -nano'),
    ("openai", "GPT-5.4-mini", "2026-03-17", '("GPT-5.4 mini" OR "5.4 mini" OR "GPT-5.4-mini" OR "5.4 nano")'),
    ("openai", "GPT-5.5", "2026-04-23", '("GPT-5.5" OR "GPT 5.5" OR gpt5.5)'),
    ("openai", "GPT-5.5-Instant", "2026-05-05", '("GPT-5.5 Instant" OR "5.5 instant")'),
    ("openai", "GPT-5.6-preview", "2026-06-26", '("GPT-5.6" OR "GPT 5.6" OR gpt5.6 OR "5.6 Sol" OR "5.6 Terra")'),
    ("openai", "GPT-5.6-public", "2026-07-09", '("GPT-5.6" OR "GPT 5.6" OR gpt5.6 OR "5.6 Sol" OR "5.6 Terra" OR "5.6 Luna")'),
    ("openai", "GPT-5.6-price", "2026-07-30", '("GPT-5.6" OR "5.6 Luna" OR "5.6 Sol") (price OR cheaper OR "80%" OR cost OR pricing)'),
    ("openai", "GPT-6-Astra", "2026-09-03", '("GPT-6" OR "GPT 6" OR GPT6 OR "GPT-6 Astra") -"GPT-6.1"'),
]
NEG = '(disappoint OR overhyped OR underwhelming OR worse OR nerf OR broken OR slow OR "rate limit" OR expensive OR bug OR regress OR "not as good" OR meh OR hype)'
VS = '(claude OR opus OR fable OR sonnet OR gemini OR grok OR deepseek OR qwen OR minimax OR kimi OR GLM OR gpt OR codex OR vs OR versus OR beats OR compare OR better OR benchmark OR "swe-bench" OR "artificial analysis" OR arena)'


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for vendor, key, day, expr in RELEASES:
        d0 = date.fromisoformat(day)
        win = f"since:{(d0 - timedelta(days=1)).isoformat()} until:{(d0 + timedelta(days=6)).isoformat()}"
        for tag, extra, pages in (("general", "", 2), ("vs", VS, 2), ("neg", NEG, 1)):
            q = f"{expr} {extra} {win} -filter:retweets"
            n0 = len(seen)
            try:
                for t in client.search_recent(q, max_pages=pages, query_type="Top"):
                    if t.author.handle in ("Kimi_Moonshot", "Zai_org", "OpenAI", "OpenAIDevs"):
                        continue
                    r = seen.setdefault(t.id, {
                        "id": t.id, "vendor": vendor, "release": key, "tags": [],
                        "url": t.url or f"https://x.com/i/status/{t.id}",
                        "text": t.text, "created": t.created_at.isoformat() if t.created_at else None,
                        "author": t.author.handle, "followers": t.author.followers,
                        "likes": t.like_count, "retweets": t.retweet_count, "views": t.view_count, "lang": t.lang,
                    })
                    if tag not in r["tags"]:
                        r["tags"].append(tag)
            except Exception as exc:  # noqa: BLE001
                print(f"{key}/{tag}: ERROR {exc}", flush=True)
            print(f"{key}/{tag}: +{len(seen)-n0} (total {len(seen)})", flush=True)
        OUT.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT.name}: {len(seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
