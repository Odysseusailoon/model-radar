"""gemini-3.8-flash / rumored Gemini 4 Pro Arena checkpoint scan (2026-09-17).

The claim under test: an anonymous Arena entry named "gemini-3.8-flash" is
actually a Gemini 4 Pro checkpoint, with a leaked benchmark table beating
GPT-6 Astra and Fable 5.1, plus RSI (recursive self-improvement) rumours.

Run: .venv/bin/python tools/gemini4_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUTPUT = ROOT / "gemini4-tweets-2026-09-17.json"

SINCE = "since:2026-09-05_00:00:00_UTC"
QUERIES = {
    "flash_handle":   (f'"gemini-3.8-flash" {SINCE} -filter:retweets', 5),
    "flash_spaced":   (f'"gemini 3.8 flash" {SINCE} -filter:retweets', 4),
    "g4pro_hyphen":   (f'"gemini-4-pro" {SINCE} -filter:retweets', 4),
    "g4pro_spaced":   (f'"gemini 4 pro" {SINCE} -filter:retweets', 5),
    "g4_generic":     (f'"gemini 4" (arena OR checkpoint OR leak OR benchmark OR stealth) {SINCE} -filter:retweets', 4),
    "arena_ctx":      (f'(gemini-3.8-flash OR "gemini 4 pro") (arena OR lmarena OR elo OR leaderboard OR battle) {SINCE}', 4),
    "bench_leak":     (f'(gemini "4 pro" OR gemini-4-pro) (deepswe OR gdpval OR "terminal-bench" OR osworld OR benchmark) {SINCE}', 4),
    "vs_rivals":      (f'(gemini-3.8-flash OR "gemini 4 pro") (astra OR fable OR gpt-6 OR claude) {SINCE}', 4),
    "pricing":        (f'("gemini 4" OR gemini-4-pro) (pricing OR "per million" OR "$2.25" OR "11.25" OR context) {SINCE}', 3),
    "rsi":            (f'(rsi OR "recursive self-improvement" OR "self-improving") (gemini OR deepmind OR google) {SINCE} min_faves:5 -filter:retweets', 4),
    "dream_rsi":      (f'"Dream-RSI" OR "DreamRSI" {SINCE}', 2),
    "gdm_official":   (f'(from:GoogleDeepMind OR from:sundarpichai OR from:demishassabis OR from:OfficialLoganK OR from:GeminiApp) {SINCE}', 4),
    "lmarena_acct":   (f'(from:lmarena_ai OR from:arena) {SINCE}', 3),
    "cancelled_35":   (f'("gemini 3.5" OR "gemini-3.5-pro") (cancel OR cancelled OR scrapped OR killed OR wsj) {SINCE}', 3),
    "cn":             (f'(gemini-3.8-flash OR "gemini 4" OR "Gemini4") (竞技场 OR 匿名 OR 实测 OR 泄露 OR 跑分 OR 谷歌) {SINCE}', 4),
    "ja_ko":          (f'(gemini-3.8-flash OR "Gemini 4 Pro") (アリーナ OR 検証 OR リーク OR 아레나 OR 유출) {SINCE}', 3),
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
