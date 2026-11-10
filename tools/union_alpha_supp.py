"""Supplemental union-alpha scan: identity evidence, router debate, Arena status, the account itself."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient

OUTPUT = ROOT / "union-alpha-supp-2026-09-17.json"
PRIOR = ROOT / "union-alpha-tweets-2026-09-17.json"
SINCE = "since:2026-09-14_00:00:00_UTC"
Q = {
  "arena_status":  (f'("union alpha" OR union-alpha) (lmarena OR "arena" OR leaderboard OR elo OR rank OR ranked OR 榜) {SINCE}', 3),
  "router_claim":  (f'("union alpha" OR union-alpha) (router OR routing OR openrouter OR proxy OR relay OR 路由 OR 套壳) {SINCE}', 4),
  "identity":      (f'("union alpha" OR union-alpha) (GLM OR zhipu OR 智谱 OR kimi OR moonshot OR qwen OR minimax OR openai OR gemini OR mistral OR llama) {SINCE}', 4),
  "plinius":       (f'from:elder_plinius (union OR alpha OR GLM OR stealth) {SINCE}', 2),
  "theo_thread":   (f'from:theo (union OR alpha OR stealth) {SINCE}', 2),
  "maria":         (f'from:maria_rcks (union OR alpha OR router) {SINCE}', 2),
  "official_acct": (f'(from:UnionAlphaAI OR from:unionalpha OR from:union_alpha OR "@UnionAlpha") {SINCE}', 2),
  "openrouter":    (f'(from:OpenRouterAI OR from:opencode) (union OR alpha OR stealth) {SINCE}', 3),
  "benchmarks":    (f'("union alpha" OR union-alpha) (bench OR terminal-bench OR swe OR aider OR score OR 分数 OR 跑分) {SINCE}', 3),
  "spain":         (f'("union alpha" OR union-alpha) (spain OR spanish OR europe OR EU OR barcelona OR 西班牙) {SINCE}', 2),
}
def _key():
    for l in (ROOT/".env").read_text().splitlines():
        if l.startswith("TWITTERAPI_KEY="): return l.split("=",1)[1].strip()
    raise SystemExit("no key")
prior = {str(r["id"]) for r in json.loads(PRIOR.read_text())} if PRIOR.exists() else set()
c = XDataClient(api_key=_key()); seen={}
for tag,(q,p) in Q.items():
    b=len(seen)
    try:
        for t in c.search_recent(q, max_pages=p):
            r=seen.setdefault(t.id,{"id":t.id,"url":t.url or f"https://x.com/i/status/{t.id}","text":t.text,
                "created":t.created_at.isoformat() if t.created_at else None,"author":t.author.handle,
                "author_name":t.author.name,"followers":t.author.followers,"likes":t.like_count,
                "views":t.view_count,"replies":t.reply_count,"matched":[],"new":str(t.id) not in prior})
            if tag not in r["matched"]: r["matched"].append(tag)
    except Exception as e: print(f"{tag}: ERROR {e}",flush=True)
    print(f"{tag}: +{len(seen)-b}, total {len(seen)}",flush=True)
rows=sorted(seen.values(),key=lambda r:(-(r.get("likes") or 0), r.get("created") or ""))
OUTPUT.write_text(json.dumps(rows,ensure_ascii=False,indent=1))
print(f"wrote {OUTPUT.name}: {len(rows)} rows ({sum(1 for r in rows if r['new'])} new)")
for r in rows[:90]:
    tx=" ".join((r.get("text") or "").split())[:260]
    print(f"{r.get('likes',0):>5}L @{r.get('author',''):<16} {r.get('created','')[:16]} [{','.join(r['matched'])}] {r['url']}\n    {tx}")
