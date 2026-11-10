"""Jev / TypeSafe AI — GTM-angle supplement scan.

First pass (tools/jev_scan.py) answered "is the product good / did the rollout work".
This pass is built for a GTM reader: distribution surfaces, the launch video,
community-built ecosystem, onboarding funnel, competitor-lab reaction, and the
non-English markets MiniMax actually sells into.

Run:
    .venv/bin/python tools/jev_gtm_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUTPUT = ROOT / "jev-gtm-tweets-2026-09-17.json"
SINCE = "since:2026-09-14_00:00:00_UTC"

QUERIES = {
    # ── distribution: where can you actually call it ──
    "gateways":   (f'(Jev OR typesafeai) (vercel OR netlify OR openrouter OR cloudflare OR bedrock OR azure OR together OR groq OR fireworks OR gateway) {SINCE} -filter:retweets', 5),
    "partner_amp":(f'(from:rauchg OR from:vercel OR from:vercel_dev OR from:Netlify OR from:OpenRouterAI) (jev OR typesafe) {SINCE}', 3),
    "integration":(f'(jev OR typesafeai) (integration OR "now supports" OR "support for" OR plugin OR SDK OR MCP OR skill) {SINCE} -filter:retweets', 4),

    # ── the launch video / creative ──
    "video":      (f'(Jev OR typesafe) (video OR "launch video" OR trailer OR ad OR "the video" OR animation) {SINCE} -filter:retweets', 4),
    "creative":   (f'(typesafeai OR jev) (allietheicon OR "doomo" OR demo OR wikirac OR doom) {SINCE} -filter:retweets', 3),

    # ── community-built ecosystem ──
    "builtwith":  (f'("built with jev" OR "using jev" OR "built on jev" OR "jev +" OR "jev powered" OR "with @typesafeai") {SINCE} -filter:retweets', 5),
    "oss":        (f'(jev OR typesafe) (github OR "open source" OR opensource OR repo OR stars OR clone OR reproduce OR openjev) {SINCE} -filter:retweets', 4),
    "browseruse": (f'(jev) (browser-use OR browseruse OR "jev-ultrafast" OR cua OR "computer use" OR gregpr07) {SINCE} -filter:retweets', 3),

    # ── onboarding funnel ──
    "onboard":    (f'(jev OR typesafeai) ("api key" OR playground OR console OR credits OR "free credits" OR docs OR cookbook OR "got in" OR "just got") {SINCE} -filter:retweets', 4),
    "discord":    (f'(jev OR typesafe) (discord OR AMA OR "town hall" OR community OR livestream OR "live with") {SINCE} -filter:retweets', 3),

    # ── competitor / peer-lab reaction ──
    "labs":       (f'(jev OR typesafeai) (OpenAI OR Anthropic OR Google OR DeepMind OR "will copy" OR "how long until" OR competitor OR moat) {SINCE} -filter:retweets', 4),
    "cn_labs":    (f'(jev OR typesafe) (Qwen OR DeepSeek OR Kimi OR Moonshot OR GLM OR Zhipu OR MiniMax OR ERNIE) {SINCE} -filter:retweets', 4),

    # ── GTM commentary itself (the meta layer) ──
    "gtm_meta":   (f'(jev OR typesafe) (launch OR rollout OR marketing OR "go to market" OR positioning OR branding OR narrative OR "how to launch" OR playbook) {SINCE} -filter:retweets', 4),
    "funding":    (f'(typesafe OR jev) (seed OR raised OR funding OR valuation OR investors OR "40M" OR "$40" OR VC) {SINCE} -filter:retweets', 3),

    # ── non-English markets ──
    "cn":         (f'(Jev OR TypeSafe) (模型 OR 发布 OR 实测 OR 决策 OR 便宜 OR 分类 OR 延迟 OR 开源 OR 营销) {SINCE} -filter:retweets', 4),
    "ja":         (f'(Jev OR TypeSafe) (モデル OR 高速 OR 発表 OR 推論 OR 判断 OR 分類) {SINCE} -filter:retweets', 3),
    "ko":         (f'(Jev OR TypeSafe) (모델 OR 발표 OR 추론 OR 분류) {SINCE} -filter:retweets', 2),
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
