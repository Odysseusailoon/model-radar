"""Targeted scan: Meta's Muse agent products (Muse Agent / Muse Code / Muse Glimmer / Meta Model API / Meta AI agent)."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUT = ROOT / "muse-agent-tweets-2026-09-17.json"
Q = {
 "muse_agent_top": ('("Muse Agent" OR "Muse Agents" OR "Meta Agent" OR "Meta Agents" OR MuseAgent) since:2026-07-01 -filter:retweets', "Top", 3),
 "muse_agent_latest": ('("Muse Agent" OR "Muse Agents" OR MuseAgent) since:2026-08-20 -filter:retweets', "Latest", 3),
 "muse_code": ('("Muse Code" OR MuseCode OR "muse-code") since:2026-08-01 -filter:retweets', "Top", 3),
 "muse_code_neg": ('("Muse Code" OR MuseCode) (bug OR broken OR slow OR bad OR worse OR disappoint OR crash OR "rate limit" OR expensive OR vs OR compare OR "claude code" OR codex OR better) since:2026-08-01 -filter:retweets', "Top", 2),
 "glimmer": ('("Muse Glimmer" OR glimmer meta OR "muse-glimmer") since:2026-08-08 -filter:retweets', "Top", 3),
 "model_api": ('("Meta Model API" OR "meta model api" OR "Meta API" muse OR "muse spark" api) since:2026-07-01 -filter:retweets', "Top", 2),
 "meta_ai_app": ('("Meta AI" (agent OR app OR whatsapp OR instagram OR glasses)) (muse OR spark) since:2026-07-01 -filter:retweets', "Top", 2),
 "sept_latest": ('(muse meta OR "muse spark" OR "muse code" OR "muse glimmer") since:2026-09-08 -filter:retweets', "Latest", 3),
 "cn": ('(Muse OR "Muse Code" OR "Muse Agent") (Meta OR 扎克伯格 OR 小扎) (智能体 OR agent OR 编程 OR 发布 OR 体验) since:2026-07-01 -filter:retweets', "Top", 2),
}
def _key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="): return line.split("=",1)[1].strip()
    raise SystemExit("no key")
def main():
    c=XDataClient(api_key=_key()); seen={}
    for tag,(q,qt,pages) in Q.items():
        n0=len(seen)
        try:
            for t in c.search_recent(q, max_pages=pages, query_type=qt):
                r=seen.setdefault(t.id,{"id":t.id,"tags":[],"url":t.url or f"https://x.com/i/status/{t.id}","text":t.text,
                    "created":t.created_at.isoformat() if t.created_at else None,"author":t.author.handle,"followers":t.author.followers,
                    "likes":t.like_count,"retweets":t.retweet_count,"views":t.view_count,"lang":t.lang})
                if tag not in r["tags"]: r["tags"].append(tag)
        except Exception as e: print(f"{tag}: ERROR {e}",flush=True)
        print(f"{tag}: +{len(seen)-n0}",flush=True)
    OUT.write_text(json.dumps(list(seen.values()),ensure_ascii=False,indent=1)); print("wrote",len(seen))
if __name__=="__main__": main()
