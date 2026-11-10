"""Muse (Meta's personal agent, launched 2026-09-08) product + marketing reaction scan."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUT = ROOT / "muse-product-tweets-2026-09-17.json"
W = "since:2026-09-06 until:2026-09-18"
Q = {
 "official": (f'from:Muse {W}', "Latest", 3),
 "wang": (f'from:alexandr_wang {W} -filter:replies', "Latest", 3),
 "top": (f'(muse) (meta OR @Muse OR "personal agent" OR invite OR "invite code" OR musebook OR "soul.md" OR "muse for mac" OR "my muse" OR wynjr) {W} -filter:retweets', "Top", 4),
 "latest": (f'(muse) (meta OR @Muse OR "invite code" OR musebook OR "muse for mac" OR "my muse") {W} -filter:retweets', "Latest", 4),
 "wow": (f'(muse) (meta OR @Muse) ("oh this is big" OR "shockingly" OR "insane" OR "mind blown" OR "first time" OR "beat" OR "ahead" OR win OR "saved me" OR "made me" OR "got me" OR "did for me") {W} -filter:retweets', "Top", 2),
 "neg": (f'(muse) (meta OR @Muse) (privacy OR "my data" OR surveillance OR creepy OR scam OR waitlist OR "no invite" OR "can\'t get" OR broken OR bug OR slow OR disappoint OR overhyped OR hype OR "not impressed" OR meh OR fake OR astroturf OR paid) {W} -filter:retweets', "Top", 2),
 "vs": (f'(muse) (meta OR @Muse) (chatgpt OR openclaw OR "claude" OR codex OR "chatgpt work" OR "astra" OR gemini OR siri OR alexa OR hermes OR compare OR vs) {W} -filter:retweets', "Top", 2),
 "product": (f'(muse) (meta OR @Muse) (phone OR call OR calendar OR email OR whatsapp OR instagram OR shopping OR refund OR booking OR "mac" OR "ios" OR android OR app OR onboarding OR memory OR persona OR personality OR "soul") {W} -filter:retweets', "Top", 2),
 "cn": (f'(Muse) (Meta OR 小扎 OR 扎克伯格) (智能体 OR 邀请码 OR 个人 OR 助理 OR 体验 OR 发布) {W} -filter:retweets', "Top", 2),
 "ja": (f'(Muse) (Meta) (エージェント OR 招待 OR 使って) {W} -filter:retweets', "Top", 1),
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
