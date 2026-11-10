"""GPT-6 Sol pre-launch signals (leaks, routing reports, expectations), Sept 2026."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUT = ROOT / "gpt6-sol-rumor-tweets-2026-09-15.json"
Q = {
    "top": ('("GPT-6 Sol" OR "GPT6 Sol" OR "Sol 6" OR "GPT-6-Sol" OR "gpt-6-sol") since:2026-08-25 -filter:retweets', "Top", 3),
    "latest": ('("GPT-6 Sol" OR "GPT6 Sol" OR "Sol 6" OR "GPT-6-Sol" OR "gpt-6-sol") since:2026-09-05 -filter:retweets', "Latest", 4),
    "routing": ('(sol) (routed OR routing OR "a/b" OR stealth OR leaked OR leak OR rumor OR rumour OR "dev day" OR devday OR "this week" OR "next week") (openai OR gpt) since:2026-09-05 -filter:retweets', "Top", 2),
    "gpt6_next": ('("GPT-6" OR GPT6) (sol OR terra OR luna OR "next model" OR "dev day" OR devday OR upcoming OR leak OR rumor) since:2026-09-06 -filter:retweets', "Top", 2),
    "cn": ('("GPT-6 Sol" OR "Sol 6" OR "GPT6 Sol") (发布 OR 泄露 OR 路由 OR 传闻 OR 模型) since:2026-08-25 -filter:retweets', "Top", 1),
}
def _key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="): return line.split("=",1)[1].strip()
    raise SystemExit("no key")
def main():
    c = XDataClient(api_key=_key()); seen = {}
    for tag,(q,qt,pages) in Q.items():
        n0=len(seen)
        try:
            for t in c.search_recent(q, max_pages=pages, query_type=qt):
                r=seen.setdefault(t.id,{"id":t.id,"tags":[],"url":t.url or f"https://x.com/i/status/{t.id}","text":t.text,
                    "created":t.created_at.isoformat() if t.created_at else None,"author":t.author.handle,"followers":t.author.followers,
                    "likes":t.like_count,"retweets":t.retweet_count,"views":t.view_count,"lang":t.lang})
                if tag not in r["tags"]: r["tags"].append(tag)
        except Exception as e: print(f"{tag}: ERROR {e}", flush=True)
        print(f"{tag}: +{len(seen)-n0}", flush=True)
    OUT.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1)); print("wrote", len(seen))
if __name__ == "__main__": main()
