"""MiniMax M3.1-Flash-Preview good-case + user-evaluation deep scan (2026-09-29).
Two name families: official (M3.1 / M3.1-Flash-Preview, launched 2026-09-27 on MiniMax Code)
and the stealth alias Space Bunny Alpha (OpenRouter/OpenCode since 2026-09-23; prior scans
cover 09-23..09-24T06Z, so SB queries here start 09-24).
Run: .venv/bin/python tools/m31_flash_scan_20260929.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUT = ROOT / 'reports/2026-09-29-m31-flash/evidence'
OUT.mkdir(parents=True, exist_ok=True)

M31 = '("M3.1" OR "M3.1-Flash" OR "M3.1 Flash" OR "MiniMax-M3.1" OR "MiniMax M3.1" OR "M3.1-Flash-Preview" OR "m3.1-flash-preview" OR "minimax-m3.1-flash")'
SB  = '("space bunny" OR "space-bunny" OR spacebunny OR #spacebunny OR "spacebunny alpha")'
S_M = 'since:2026-09-23'
S_SB = 'since:2026-09-24_06:00:00_UTC'
NR = '-filter:retweets'
BUILT = '(built OR build OR made OR created OR shipped OR "one shot" OR "one-shot" OR oneshot OR "from scratch" OR "single prompt" OR prototype OR clone OR game OR "landing page" OR dashboard OR app)'
FIXED = '(fixed OR solved OR debug OR debugged OR refactor OR refactored OR migrated OR migration OR "figured out" OR bug OR bugs OR tests OR "test suite" OR CI)'
AGENT = '(agent OR agents OR subagent OR subagents OR "sub agent" OR "sub-agents" OR harness OR "tool call" OR "tool calls" OR "tool calling" OR mcp OR plugin OR workflow OR orchestrat OR "lead agent" OR swarm)'
LONG  = '(pdf OR codebase OR repo OR repository OR "entire" OR "whole" OR "1m" OR "1M context" OR "long context" OR document OR docs OR "million tokens" OR "context window")'
MM    = '(video OR image OR screenshot OR vision OR ocr OR figma OR "from a photo" OR mockup OR "reference image" OR multimodal OR 3d OR three.js OR threejs OR webgl OR shader)'
PRAISE= '(impressive OR impressed OR insane OR amazing OR incredible OR "blown away" OR surprised OR "actually good" OR "really good" OR underrated OR wow OR crazy OR banger OR "10x" OR nailed OR flawless OR perfect OR solid OR "pretty good" OR "very good" OR love OR loving)'
WINS  = '(beats OR beat OR "better than" OR outperform OR outperforms OR won OR wins OR "on par" OR "as good as" OR "close to" OR "same level" OR "comparable")'
NEG   = '(slow OR latency OR timeout OR broken OR fails OR failed OR failing OR loop OR looping OR stuck OR worse OR bad OR terrible OR hallucinat OR hallucination OR disappointed OR disappointing OR garbage OR mid OR overrated OR "not good" OR "not great" OR meh OR trash OR unusable OR lazy OR dumb OR regress)'
CMP   = '(vs OR versus OR compared OR comparison OR "head to head" OR benchmark OR benchmarks OR tested OR eval OR evals OR "side by side" OR sonnet OR opus OR fable OR "gpt-6" OR gpt6 OR gemini OR glm OR deepseek OR mimo OR kimi OR qwen OR grok OR codex OR "claude code")'
PRICE = '(price OR pricing OR cost OR costs OR cheap OR cheaper OR expensive OR free OR unlimited OR credits OR "token plan" OR "m plan" OR subscription OR subscribe OR subscribed OR plan OR tier OR "check-in" OR "check in" OR "per million" OR openrouter OR api)'
SPEED = '(fast OR faster OR speed OR "tok/s" OR "tokens/s" OR "tokens per second" OR tps OR quick OR snappy OR latency OR slow OR ttft OR throughput OR responsive)'
CHAN  = '(opencode OR "open code" OR openrouter OR cline OR kilo OR kilocode OR roo OR "claude code" OR "minimax code" OR zcode OR "z code" OR droid OR crush OR cursor OR windsurf OR "zed" OR aider OR hermes OR goose OR "codex cli" OR copilot)'
IDENT = '(stealth OR "is minimax" OR "== minimax" OR "is m3.1" OR "turns out" OR revealed OR reveal OR unveiled OR "actually minimax" OR "was minimax" OR identity OR "who made" OR "behind it")'

Q = []
def add(tag, query, modes=('Latest','Top'), pages=3):
    Q.append(dict(tag=tag, query=query, modes=list(modes), max_pages=pages))

# --- A. official + launch-post replies/quotes ---------------------------------
add('off_agent',  f'from:MiniMaxAgent since:2026-09-25', ('Latest',), 3)
add('off_mm',     f'(from:MiniMax_AI OR from:Hailuo_AI OR from:MiniMax__AI) since:2026-09-23', ('Latest',), 3)
add('to_off',     f'(to:MiniMaxAgent OR to:MiniMax_AI) since:2026-09-27 {NR}', ('Latest',), 5)
add('quote_off',  f'(quoted_tweet_id:2104217000000000000 OR "MiniMaxAgent/status") since:2026-09-27 {NR}', ('Latest',), 1)  # placeholder, replaced below at runtime

# --- B. M3.1 by angle ---------------------------------------------------------
add('m31_all_latest', f'{M31} {S_M} {NR}', ('Latest',), 8)
add('m31_all_top',    f'{M31} {S_M} {NR}', ('Top',), 5)
add('m31_built',  f'{M31} {BUILT} {S_M} {NR}')
add('m31_fixed',  f'{M31} {FIXED} {S_M} {NR}')
add('m31_agent',  f'{M31} {AGENT} {S_M} {NR}')
add('m31_long',   f'{M31} {LONG} {S_M} {NR}')
add('m31_mm',     f'{M31} {MM} {S_M} {NR}')
add('m31_praise', f'{M31} {PRAISE} {S_M} {NR}')
add('m31_wins',   f'{M31} {WINS} {S_M} {NR}')
add('m31_neg',    f'{M31} {NEG} {S_M} {NR}')
add('m31_cmp',    f'{M31} {CMP} {S_M} {NR}')
add('m31_price',  f'{M31} {PRICE} {S_M} {NR}')
add('m31_speed',  f'{M31} {SPEED} {S_M} {NR}')
add('m31_chan',   f'{M31} {CHAN} {S_M} {NR}')
add('m31_media',  f'{M31} filter:media {S_M} {NR}')
add('m31_video',  f'{M31} filter:native_video {S_M} {NR}')
add('m31_links',  f'{M31} filter:links -filter:media {S_M} {NR}')

# --- C. Space Bunny alias, day 2..7 ------------------------------------------
add('sb_all_latest', f'{SB} {S_SB} {NR}', ('Latest',), 8)
add('sb_all_top',    f'{SB} {S_SB} {NR}', ('Top',), 5)
add('sb_built',  f'{SB} {BUILT} {S_SB} {NR}')
add('sb_fixed',  f'{SB} {FIXED} {S_SB} {NR}')
add('sb_agent',  f'{SB} {AGENT} {S_SB} {NR}')
add('sb_long',   f'{SB} {LONG} {S_SB} {NR}')
add('sb_mm',     f'{SB} {MM} {S_SB} {NR}')
add('sb_praise', f'{SB} {PRAISE} {S_SB} {NR}')
add('sb_wins',   f'{SB} {WINS} {S_SB} {NR}')
add('sb_neg',    f'{SB} {NEG} {S_SB} {NR}')
add('sb_cmp',    f'{SB} {CMP} {S_SB} {NR}')
add('sb_price',  f'{SB} {PRICE} {S_SB} {NR}')
add('sb_speed',  f'{SB} {SPEED} {S_SB} {NR}')
add('sb_chan',   f'{SB} {CHAN} {S_SB} {NR}')
add('sb_ident',  f'({SB} OR {M31}) {IDENT} {S_SB} {NR}')
add('sb_media',  f'{SB} filter:media {S_SB} {NR}')
add('sb_video',  f'{SB} filter:native_video {S_SB} {NR}')
add('sb_links',  f'{SB} filter:links -filter:media {S_SB} {NR}')

# --- D. generic MiniMax coding chatter (catches "minimax flash", "minimax code") --
add('mx_code',   f'(minimax OR "minimax code" OR minimaxagent) (flash OR "m3.1" OR "token plan" OR "m plan" OR unlimited OR "check-in" OR coding OR agent OR opencode OR openrouter) since:2026-09-26 {NR}', ('Latest','Top'), 4)
add('mx_flash',  f'("minimax flash" OR "minimax\'s flash" OR "minimax m3" OR "minimax-m3") since:2026-09-26 {NR}', ('Latest','Top'), 3)

# --- E. partners / channels --------------------------------------------------
PART = '(from:opencode OR from:cline OR from:OpenRouterAI OR from:OpenRouter OR from:kilocode OR from:ollama OR from:vllm_project OR from:sglproject OR from:LMStudioAI OR from:UnslothAI OR from:FireworksAI_HQ OR from:basetenco OR from:togethercompute OR from:novita_labs OR from:ArtificialAnlys OR from:lmarena_ai OR from:vercel OR from:aihubmix OR from:zeddotdev OR from:FactoryAI)'
add('partners',  f'{PART} (minimax OR "M3.1" OR "space bunny" OR spacebunny) since:2026-09-23', ('Latest',), 4)

# --- F. non-English ----------------------------------------------------------
ZHN = '(M3.1 OR "M3.1-Flash" OR "space bunny" OR spacebunny OR 太空兔 OR 海螺 OR MiniMax)'
add('zh',     f'{ZHN} (做了 OR 一次 OR 实测 OR 成功 OR 惊艳 OR 不错 OR 好用 OR 搞定 OR 修好 OR 体验 OR 对比 OR 评测 OR 便宜 OR 免费 OR 无限 OR 订阅 OR 翻车 OR 拉胯 OR 一般 OR 失望 OR 慢 OR 快) lang:zh since:2026-09-23 {NR}', ('Latest','Top'), 5)
add('zh_all', f'("M3.1" OR "space bunny" OR spacebunny OR "MiniMax Code") lang:zh since:2026-09-23 {NR}', ('Latest','Top'), 4)
add('ja',     f'("M3.1" OR "space bunny" OR spacebunny OR スペースバニー OR MiniMax) (作った OR 一発 OR 検証 OR すごい OR 良い OR 速い OR できた OR 試した OR 比較 OR 無料 OR 使ってみた OR 微妙 OR ダメ OR 遅い) lang:ja since:2026-09-23 {NR}', ('Latest','Top'), 4)
add('ko',     f'("M3.1" OR "space bunny" OR spacebunny OR 스페이스버니 OR 미니맥스 OR MiniMax) lang:ko since:2026-09-23 {NR}', ('Latest','Top'), 3)
add('es_pt',  f'("M3.1" OR "space bunny" OR spacebunny OR MiniMax) (gratis OR grátis OR probé OR testei OR prueba OR teste OR modelo OR increíble OR incrível OR mejor OR melhor OR barato) (lang:es OR lang:pt) since:2026-09-23 {NR}', ('Latest','Top'), 3)
add('other',  f'("M3.1" OR "space bunny" OR spacebunny) (lang:fr OR lang:de OR lang:ru OR lang:vi OR lang:id OR lang:tr OR lang:it OR lang:hi) since:2026-09-23 {NR}', ('Latest','Top'), 3)

def _key():
    for line in (ROOT/'.env').read_text().splitlines():
        if line.startswith('TWITTERAPI_KEY='): return line.split('=',1)[1].strip().strip('"').strip("'")
    raise SystemExit('no key')

def row(t, stamp):
    return dict(id=t.id, url=t.url or f'https://x.com/i/status/{t.id}', text=t.text,
                created=t.created_at.isoformat() if t.created_at else None, lang=t.lang,
                author=t.author.handle, author_name=t.author.name, followers=t.author.followers,
                likes=t.like_count, retweets=t.retweet_count, replies=t.reply_count,
                quotes=t.quote_count, views=t.view_count, media=t.raw.get('extendedEntities',{}).get('media',[]) and [m.get('type') for m in t.raw.get('extendedEntities',{}).get('media',[])],
                urls=[u.get('expanded_url') for u in (t.raw.get('entities',{}) or {}).get('urls',[]) if u.get('expanded_url')],
                in_reply_to=t.raw.get('inReplyToId'), conversation_id=t.raw.get('conversationId'),
                quoted_id=(t.raw.get('quoted_tweet') or {}).get('id'), matched=[], collected_at=stamp)

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--prefixes', default=''); ap.add_argument('--suffix', default='')
    a=ap.parse_args()
    global OUT
    pref=[x for x in a.prefixes.split(',') if x]
    c = XDataClient(api_key=_key())
    # resolve launch-post ids for quote/reply harvesting
    launch_ids = []
    try:
        for t in c.search_recent('from:MiniMaxAgent since:2026-09-26 -filter:retweets', query_type='Latest', max_pages=2):
            if (t.like_count or 0) >= 150: launch_ids.append(t.id)
        for t in c.search_recent('from:MiniMax_AI since:2026-09-26 -filter:retweets', query_type='Latest', max_pages=1):
            if (t.like_count or 0) >= 150: launch_ids.append(t.id)
    except Exception as e: print('launch id resolve ERR', e, flush=True)
    launch_ids = launch_ids[:6]
    print('launch ids', launch_ids, flush=True)
    for i, q in enumerate(Q):
        if q['tag']=='quote_off':
            q['query'] = '(' + ' OR '.join(f'quoted_tweet_id:{i}' for i in launch_ids) + f') {NR}' if launch_ids else None
            q['max_pages']=4
    for lid in launch_ids:
        Q.append(dict(tag=f'conv_{lid}', query=f'conversation_id:{lid} since:2026-09-26', modes=['Latest'], max_pages=4))
    if pref: Q[:] = [q for q in Q if any(q['tag'].startswith(x) for x in pref)]
    manifest_path = OUT/f'queries{a.suffix}.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    done = {(m['tag'], m['mode']) for m in manifest if m.get('status')=='ok'}
    merged_path = OUT/f'merged{a.suffix}.json'
    seen = {r['id']: r for r in json.loads(merged_path.read_text())} if merged_path.exists() else {}
    for q in Q:
        if not q['query']: continue
        for mode in q['modes']:
            if (q['tag'], mode) in done: continue
            stamp = datetime.now(timezone.utc).isoformat(); rows=[]; status='ok'; err=None
            try:
                for t in c.search_recent(q['query'], query_type=mode, max_pages=q['max_pages']):
                    r = seen.setdefault(t.id, row(t, stamp))
                    k=f"{q['tag']}:{mode[0]}"
                    if k not in r['matched']: r['matched'].append(k)
                    rows.append(t.id)
            except Exception as e:
                status='error'; err=f'{type(e).__name__}: {e}'[:200]
            manifest.append(dict(tag=q['tag'], mode=mode, query=q['query'], status=status, error=err, count=len(rows), collected_at=stamp))
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
            merged_path.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1))
            print(f"{q['tag']}/{mode}: {status} {len(rows)} total {len(seen)}", flush=True)
    print('COMPLETE', len(seen), flush=True)
if __name__=='__main__': main()
