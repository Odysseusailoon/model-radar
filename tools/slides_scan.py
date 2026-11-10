"""Scan X for the 'AI slides / editable design assets' angle:
Genspark AI Slides & Design, MiniMax Design, GPT-6 Astra editable/vector output,
and the pain of AI output that is not editable.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient

OUT = ROOT / "slides-tweets-2026-09-06.json"

QUERIES = {
    "gs_slides": ('("genspark ai slides" OR "genspark slides" OR "genspark ai designer" OR "genspark design") -filter:retweets', "Top"),
    "gs_slides_latest": ('(genspark) (slides OR deck OR presentation OR designer) -filter:retweets', "Latest"),
    "editable_pain": ('("not editable" OR "non-editable" OR "actually editable" OR "editable slides" OR "editable layers" OR "editable vector") (ai OR generated OR slides OR design OR figma OR canva) -filter:retweets', "Top"),
    "astra_editable": ('("gpt-6" OR astra) (svg OR vector OR editable OR figma OR canva OR pptx OR keynote OR "design tokens") -filter:retweets', "Top"),
    "astra_slides": ('("gpt-6" OR astra) (slides OR deck OR presentation OR pitch) -filter:retweets', "Top"),
    "mm_design": ('("minimax design" OR #MiniMaxDesign) -filter:retweets', "Top"),
    "ai_slides_rivals": ('(gamma OR beautiful.ai OR tome OR "napkin ai" OR canva OR figma) (ai slides OR "ai deck" OR agent) -filter:retweets', "Top"),
    "video_to_asset": ('(video OR clip) ("into slides" OR "into a deck" OR storyboard OR "keyframe" OR "extract frames") ai -filter:retweets', "Top"),
    "m31_slides": ('(minimax) (slides OR deck OR presentation OR design OR pptx) -filter:retweets', "Top"),
    "genoffice": ('(genoffice OR "gen office") -filter:retweets', "Top"),
    "slides_agent": ('("slides agent" OR "deck agent" OR "one prompt" deck OR "prompt to deck" OR "prompt to slides") -filter:retweets', "Top"),
    "brand_kit": ('("brand kit" OR "brand guidelines" OR "design system") (ai OR agent OR generated OR llm) -filter:retweets', "Top"),
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
                    "id": t.id, "url": t.url or f"https://x.com/i/status/{t.id}",
                    "text": t.text,
                    "created": t.created_at.isoformat() if t.created_at else None,
                    "author": t.author.handle, "author_name": t.author.name,
                    "followers": t.author.followers, "likes": t.like_count,
                    "retweets": t.retweet_count, "views": t.view_count, "matched": [],
                })
                if tag not in rec["matched"]:
                    rec["matched"].append(tag)
        except Exception as exc:  # noqa: BLE001
            print(f"{tag}: ERROR {exc}")
        print(f"{tag}: +{len(seen)-n0} (total {len(seen)})", flush=True)
    tweets = sorted(seen.values(), key=lambda r: -(r.get("likes") or 0))
    OUT.write_text(json.dumps(tweets, ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT.name}: {len(tweets)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
