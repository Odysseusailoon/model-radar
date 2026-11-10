"""Space Bunny scan keyed to the internal M3.1 front-end market eval (3D/Web/Chart/Game/SVG + harness). 2026-09-24.
Run: .venv/bin/python tools/spacebunny_frontend_scan.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUTPUT = ROOT / "spacebunny-frontend-2026-09-24.json"
S = "since:2026-09-23_00:00:00_UTC"
B = '("space bunny" OR "space-bunny" OR spacebunny OR #spacebunny)'
Q = {
 "3d":      f'{B} ("3d" OR threejs OR "three.js" OR webgl OR voxel OR blender OR "3D scene" OR pagoda OR babylon OR "r3f") {S} -filter:retweets',
 "web":     f'{B} (website OR "landing page" OR "web app" OR webapp OR saas OR dashboard OR portfolio OR "single html" OR "one html" OR "html file" OR tailwind OR react OR nextjs OR "next.js") {S} -filter:retweets',
 "chart":   f'{B} (chart OR charts OR graph OR plot OR visualization OR visualisation OR infographic OR d3 OR plotly OR "data viz" OR research OR report OR analysis OR analyze) {S} -filter:retweets',
 "game":    f'{B} (game OR games OR minecraft OR mario OR shooter OR platformer OR runner OR arcade OR "playable" OR sonic OR gta OR tetris OR snake OR pong OR "boss fight") {S} -filter:retweets',
 "svg":     f'{B} (svg OR pelican OR peacock OR "vector" OR icon OR icons OR logo OR illustration) {S} -filter:retweets',
 "harness": f'{B} ("claude code" OR opencode OR "open code" OR cline OR "kilo" OR cursor OR codex OR "roo code" OR aider OR "pi coding" OR "command code" OR hermes OR windsurf OR "openclaw" OR "which harness" OR "in cursor" OR "in cline") {S} -filter:retweets',
 "compare": f'{B} ("deepseek" OR "ds 4.1" OR "v4.1" OR "glm" OR "5.3 flash" OR "mimo" OR "gemini" OR "flash") (vs OR versus OR compare OR compared OR "side by side" OR beats OR beat OR better OR worse OR same OR "on par") {S} -filter:retweets',
 "recent":  f'{B} since:2026-09-24_05:00:00_UTC -filter:retweets',
 "ja":      f'("space bunny" OR スペースバニー) (3D OR ゲーム OR SVG OR グラフ OR フロント OR サイト OR 比較 OR Claude OR opencode) {S}',
 "cn":      f'("space bunny" OR spacebunny) (3D OR 游戏 OR SVG OR 图表 OR 前端 OR 网页 OR 对比 OR 横评 OR 环境 OR "claude code") {S}',
}
def _key():
    for l in (ROOT/".env").read_text().splitlines():
        if l.startswith("TWITTERAPI_KEY="): return l.split("=",1)[1].strip()
    raise SystemExit("no key")
def main():
    c=XDataClient(api_key=_key()); seen={}
    for tag,q in Q.items():
        for qt in ("Latest","Top"):
            b=len(seen)
            try:
                for t in c.search_recent(q,max_pages=3,query_type=qt):
                    r=seen.setdefault(t.id,{"id":t.id,"url":t.url or f"https://x.com/i/status/{t.id}","text":t.text,"created":t.created_at.isoformat() if t.created_at else None,"lang":t.lang,"author":t.author.handle,"followers":t.author.followers,"likes":t.like_count,"retweets":t.retweet_count,"replies":t.reply_count,"views":t.view_count,"matched":[]})
                    k=f"{tag}:{qt[0]}"
                    if k not in r["matched"]: r["matched"].append(k)
            except Exception as e: print(f"{tag}/{qt}: ERROR {e}",flush=True)
            print(f"{tag}/{qt}: +{len(seen)-b} total {len(seen)}",flush=True)
    rows=sorted(seen.values(),key=lambda r:(-(r.get("likes") or 0),r.get("created") or ""))
    OUTPUT.write_text(json.dumps(rows,ensure_ascii=False,indent=1)); print("wrote",OUTPUT.name,len(rows))
if __name__=="__main__": main()
