"""Meta Muse (Muse Spark) product + marketing scan, Mar-Sep 2026."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUT = ROOT / "muse-tweets-2026-09-17.json"
M = '("Muse Spark" OR "Meta Muse" OR (muse meta) OR (muse "meta ai") OR MuseSpark OR "Muse 1.3" OR "Muse 1.2" OR "Muse 1.1")'
MONTHS = [("2026-03-15","2026-04-15"),("2026-04-15","2026-05-15"),("2026-05-15","2026-06-15"),("2026-06-15","2026-07-15"),("2026-07-15","2026-08-15"),("2026-08-15","2026-09-18")]
ACCTS = ["AIatMeta","Meta","alexandr_wang","zuck"]
G = {
 "general": ("", "Top", 2),
 "product": ('(app OR whatsapp OR instagram OR messenger OR glasses OR "ray-ban" OR rayban OR oakley OR "meta ai" OR feature OR voice OR agent OR "computer use" OR api OR developer OR pricing OR free OR subscription)', "Top", 2),
 "mkt": ('(ad OR ads OR campaign OR billboard OR commercial OR superbowl OR "super bowl" OR creator OR influencer OR launch OR event OR keynote OR "LlamaCon" OR connect OR hype OR marketing OR brand)', "Top", 1),
 "vs": ('(gpt OR openai OR claude OR anthropic OR fable OR opus OR gemini OR google OR grok OR deepseek OR kimi OR GLM OR qwen OR llama OR "open source" OR "open weights" OR benchmark OR arena OR "artificial analysis" OR vs)', "Top", 2),
 "neg": ('(disappoint OR flop OR overhyped OR worse OR bad OR censored OR refus OR hallucinat OR nerf OR "not open" OR closed OR abandon OR layoff OR drama OR leaving OR quit OR fail OR meh OR trash OR wrapper)', "Top", 1),
 "cn": ('(模型 OR 发布 OR 体验 OR 测评 OR 闭源 OR 开源 OR 广告 OR 眼镜)', "Top", 1),
}
def _key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="): return line.split("=",1)[1].strip()
    raise SystemExit("no key")
def rec(t,tag,phase):
    return {"id":t.id,"tags":[tag],"phase":phase,"url":t.url or f"https://x.com/i/status/{t.id}","text":t.text,
            "created":t.created_at.isoformat() if t.created_at else None,"author":t.author.handle,"followers":t.author.followers,
            "likes":t.like_count,"retweets":t.retweet_count,"views":t.view_count,"lang":t.lang}
def main():
    c=XDataClient(api_key=_key()); seen={}
    for since,until in MONTHS:
        win=f"since:{since} until:{until}"
        for a in ACCTS:
            n0=len(seen)
            try:
                for t in c.search_recent(f"from:{a} (muse OR spark OR model OR ai) {win} -filter:replies", max_pages=2, query_type="Latest"):
                    seen.setdefault(t.id, rec(t,f"acct:{a}",since))
            except Exception as e: print(f"{since} {a}: ERROR {e}",flush=True)
            print(f"{since} from:{a}: +{len(seen)-n0}",flush=True)
        for tag,(extra,qt,pages) in G.items():
            n0=len(seen)
            try:
                for t in c.search_recent(f"{M} {extra} {win} -filter:retweets", max_pages=pages, query_type=qt):
                    r=seen.setdefault(t.id, rec(t,tag,since))
                    if tag not in r["tags"]: r["tags"].append(tag)
            except Exception as e: print(f"{since} {tag}: ERROR {e}",flush=True)
            print(f"{since} {tag}: +{len(seen)-n0}",flush=True)
        OUT.write_text(json.dumps(list(seen.values()),ensure_ascii=False,indent=1))
    print("wrote",len(seen))
if __name__=="__main__": main()
