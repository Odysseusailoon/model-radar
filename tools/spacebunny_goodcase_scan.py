"""Space Bunny Alpha good-case deep scan (2026-09-23): outcome-oriented queries,
Latest + Top channels, media/links filters, replies to the two launch posts.
Run: .venv/bin/python tools/spacebunny_goodcase_scan.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUTPUT = ROOT / "spacebunny-goodcase-2026-09-23.json"
SINCE = "since:2026-09-23_00:00:00_UTC"
BASE = '("space bunny" OR "space-bunny" OR spacebunny OR #spacebunny)'
Q = {
 "built":     f'{BASE} (built OR build OR made OR created OR shipped OR "one shot" OR "one-shot" OR oneshot OR "from scratch" OR "single prompt") {SINCE} -filter:retweets',
 "fixed":     f'{BASE} (fixed OR solved OR debug OR debugged OR refactor OR migrated OR "figured out" OR bug) {SINCE} -filter:retweets',
 "agentic":   f'{BASE} (agent OR agents OR subagent OR "sub agent" OR "sub-agents" OR harness OR "tool call" OR "tool calls" OR mcp OR plugin OR workflow) {SINCE} -filter:retweets',
 "longctx":   f'{BASE} (pdf OR codebase OR repo OR repository OR "entire" OR "whole" OR "1m" OR "long context" OR document OR docs) {SINCE} -filter:retweets',
 "multimodal":f'{BASE} (video OR image OR screenshot OR vision OR ocr OR figma OR "from a photo" OR mockup) {SINCE} -filter:retweets',
 "praise":    f'{BASE} (impressive OR impressed OR insane OR amazing OR incredible OR "blown away" OR surprised OR "actually good" OR "really good" OR underrated OR wow OR crazy OR banger OR "10x" OR nailed OR flawless OR perfect) {SINCE} -filter:retweets',
 "wins":      f'{BASE} (beats OR beat OR "better than" OR outperform OR won OR wins OR "on par" OR "as good as" OR "close to") {SINCE} -filter:retweets',
 "media":     f'{BASE} filter:media {SINCE} -filter:retweets',
 "videos":    f'{BASE} filter:native_video {SINCE} -filter:retweets',
 "links":     f'{BASE} filter:links -filter:media {SINCE} -filter:retweets',
 "reply_oc":  f'conversation_id:2102767716666941864 {SINCE}',
 "reply_or":  f'conversation_id:2102772427105407270 {SINCE}',
 "cn":        f'("space bunny" OR spacebunny OR 太空兔) (做了 OR 一次 OR 实测 OR 成功 OR 惊艳 OR 不错 OR 好用 OR 秒 OR 一把 OR 搞定 OR 修好) {SINCE}',
 "ja":        f'("space bunny" OR スペースバニー) (作った OR 一発 OR 検証 OR すごい OR 良い OR 速い OR できた) {SINCE}',
}
def _key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="): return line.split("=",1)[1].strip()
    raise SystemExit("no key")
def main():
    c = XDataClient(api_key=_key()); seen = {}
    for tag,q in Q.items():
        for qt in ("Latest","Top"):
            b=len(seen)
            try:
                for t in c.search_recent(q, max_pages=3, query_type=qt):
                    r = seen.setdefault(t.id, {"id":t.id,"url":t.url or f"https://x.com/i/status/{t.id}","text":t.text,
                        "created":t.created_at.isoformat() if t.created_at else None,"lang":t.lang,"author":t.author.handle,
                        "author_name":t.author.name,"followers":t.author.followers,"likes":t.like_count,"retweets":t.retweet_count,
                        "replies":t.reply_count,"views":t.view_count,"matched":[]})
                    k=f"{tag}:{qt[0]}"
                    if k not in r["matched"]: r["matched"].append(k)
            except Exception as e: print(f"{tag}/{qt}: ERROR {e}", flush=True)
            print(f"{tag}/{qt}: +{len(seen)-b} total {len(seen)}", flush=True)
    rows=sorted(seen.values(), key=lambda r:(-(r.get("likes") or 0), r.get("created") or ""))
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1)); print("wrote", OUTPUT.name, len(rows))
if __name__=="__main__": main()
