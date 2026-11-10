"""MiniMax M3.1 Flash public launch (2026-10-19) — first-hours X scan.
Timeline anchors (UTC): 09:21 teaser "Welcome back. Space Bunny" (2112111925975032241);
11:56 main launch post (2112150867868541221); 12:16 @MiniMaxAgent intro (2112155992708538688);
12:19 offers (2112156691492131012); 20:36-20:59 partner thank-you posts (ollama/opencode/openrouter/cline).
Run: TWITTERAPI_MIN_INTERVAL=1.2 .venv/bin/python tools/m31_flash_launch_scan_20261019.py --prefixes m31_,sb_ --suffix -a
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient
OUT = ROOT / 'reports/2026-10-19-m31-flash-launch/evidence'
OUT.mkdir(parents=True, exist_ok=True)

M31 = '("M3.1" OR "M3.1-Flash" OR "M3.1 Flash" OR "MiniMax-M3.1" OR "MiniMax M3.1" OR "m3.1-flash" OR "minimax-m3.1-flash" OR "M3.1Flash" OR "m31 flash")'
SB  = '("space bunny" OR "space-bunny" OR spacebunny OR #spacebunny OR "spacebunny alpha")'
MXF = '("minimax flash" OR "minimax\'s flash" OR "minimax m3" OR "minimax-m3" OR "minimax new model" OR "minimax\'s new model" OR "minimax just" OR "minimax released" OR "minimax launched" OR "minimax dropped")'
SINCE = 'since:2026-10-19_08:00:00_UTC'
NR = '-filter:retweets'
BUILT = '(built OR build OR made OR created OR shipped OR "one shot" OR "one-shot" OR oneshot OR "from scratch" OR "single prompt" OR prototype OR clone OR game OR "landing page" OR dashboard OR app OR website OR demo)'
FIXED = '(fixed OR solved OR debug OR debugged OR refactor OR refactored OR migrated OR migration OR "figured out" OR bug OR bugs OR tests OR "test suite" OR CI OR PR OR "pull request")'
AGENT = '(agent OR agents OR subagent OR subagents OR "sub agent" OR "sub-agents" OR harness OR "tool call" OR "tool calls" OR "tool calling" OR mcp OR plugin OR workflow OR orchestrat OR "lead agent" OR swarm OR "agentic")'
LONG  = '(pdf OR codebase OR repo OR repository OR "entire" OR "whole" OR "1m" OR "1M context" OR "long context" OR document OR docs OR "million tokens" OR "context window")'
MM    = '(video OR image OR screenshot OR vision OR ocr OR figma OR "from a photo" OR mockup OR "reference image" OR multimodal OR 3d OR three.js OR threejs OR webgl OR shader)'
PRAISE= '(impressive OR impressed OR insane OR amazing OR incredible OR "blown away" OR surprised OR "actually good" OR "really good" OR underrated OR wow OR crazy OR banger OR "10x" OR nailed OR flawless OR perfect OR solid OR "pretty good" OR "very good" OR love OR loving OR goated OR cooked OR "cooking")'
WINS  = '(beats OR beat OR "better than" OR outperform OR outperforms OR won OR wins OR "on par" OR "as good as" OR "close to" OR "same level" OR "comparable" OR "matches" OR "sota")'
NEG   = '(slow OR latency OR timeout OR broken OR fails OR failed OR failing OR loop OR looping OR stuck OR worse OR bad OR terrible OR hallucinat OR hallucination OR disappointed OR disappointing OR garbage OR mid OR overrated OR "not good" OR "not great" OR meh OR trash OR unusable OR lazy OR dumb OR regress OR "rate limit" OR "rate limited" OR error OR errors OR 429 OR down OR outage OR "doesn\'t work" OR "does not work" OR nerf OR nerfed OR "benchmaxx" OR benchmaxxed OR "benchmark maxing")'
CMP   = '(vs OR versus OR compared OR comparison OR "head to head" OR benchmark OR benchmarks OR tested OR eval OR evals OR "side by side" OR sonnet OR opus OR fable OR "gpt-6" OR gpt6 OR gemini OR glm OR deepseek OR mimo OR kimi OR qwen OR grok OR codex OR "claude code" OR haiku OR "swe-bench" OR "terminal-bench" OR "terminal bench" OR arena OR "artificial analysis")'
PRICE = '(price OR pricing OR cost OR costs OR cheap OR cheaper OR expensive OR free OR unlimited OR credits OR "token plan" OR "m plan" OR subscription OR subscribe OR subscribed OR plan OR tier OR "per million" OR "$0.15" OR "0.15" OR "cents" OR "per task" OR "70%" OR "98%" OR "economics")'
SPEED = '(fast OR faster OR speed OR "tok/s" OR "tokens/s" OR "tokens per second" OR tps OR quick OR snappy OR latency OR slow OR ttft OR throughput OR responsive OR "170" OR "3x")'
CHAN  = '(opencode OR "open code" OR openrouter OR cline OR kilo OR kilocode OR roo OR "claude code" OR "minimax code" OR zcode OR droid OR crush OR cursor OR windsurf OR zed OR aider OR hermes OR goose OR "codex cli" OR copilot OR ollama OR vercel OR "ai gateway" OR "ai sdk" OR together OR fireworks OR baseten OR novita OR groq OR cerebras OR antseed OR "lm studio" OR continue OR "pi coding" OR factory OR "oh my opencode" OR omo)'
IDENT = '(stealth OR "was space bunny" OR "is space bunny" OR "space bunny was" OR "space bunny is" OR "turns out" OR revealed OR reveal OR unveiled OR "actually minimax" OR "was minimax" OR "early build" OR "earlier version" OR "early version" OR "200T" OR "200 trillion" OR confirmed OR "called it")'
WEIGHTS = '(weights OR "open weights" OR "open-weights" OR "open source" OR opensource OR "open-source" OR huggingface OR "hugging face" OR "hf" OR "428B" OR "428b" OR params OR parameters OR "active params" OR moe OR "mixture of experts" OR license OR "closed")'
TRUST = '(china OR chinese OR ccp OR "data retention" OR "zero data" OR privacy OR "US-hosted" OR "us hosted" OR hosted OR sovereignty OR "trust" OR "safe" OR "security" OR "censor" OR "censored")'

Q = []
def add(tag, query, modes=('Latest','Top'), pages=3):
    Q.append(dict(tag=tag, query=query, modes=list(modes), max_pages=pages))

# --- A. official posts, replies, quotes, conversation threads ------------------
add('off_all',  f'(from:MiniMaxAgent OR from:MiniMax_AI OR from:Hailuo_AI OR from:MiniMax__AI) since:2026-10-18', ('Latest',), 3)
add('to_off',   f'(to:MiniMaxAgent OR to:MiniMax_AI) {SINCE} {NR}', ('Latest',), 8)
LAUNCH_IDS = ['2112150867868541221','2112111925975032241','2112155992708538688','2112156691492131012','2112154695578095884','2112152630617337952','2112282114150547819','2112287025361801272','2112287494876373432','2112281693642227753']
add('quote_off', '(' + ' OR '.join(f'quoted_tweet_id:{i}' for i in LAUNCH_IDS[:6]) + f') {NR}', ('Latest',), 8)
add('quote_off2', '(' + ' OR '.join(f'quoted_tweet_id:{i}' for i in LAUNCH_IDS[6:]) + f') {NR}', ('Latest',), 3)
for lid in LAUNCH_IDS[:4]:
    add(f'conv_{lid}', f'conversation_id:{lid} since:2026-10-19', ('Latest',), 6)

# --- B. M3.1 by angle ------------------------------------------------------------
add('m31_all_latest', f'{M31} {SINCE} {NR}', ('Latest',), 20)
add('m31_all_top',    f'{M31} {SINCE} {NR}', ('Top',), 8)
add('m31_en_latest',  f'{M31} lang:en {SINCE} {NR}', ('Latest',), 20)
add('m31_built',  f'{M31} {BUILT} {SINCE} {NR}', pages=5)
add('m31_fixed',  f'{M31} {FIXED} {SINCE} {NR}', pages=4)
add('m31_agent',  f'{M31} {AGENT} {SINCE} {NR}', pages=5)
add('m31_long',   f'{M31} {LONG} {SINCE} {NR}', pages=3)
add('m31_mm',     f'{M31} {MM} {SINCE} {NR}', pages=3)
add('m31_praise', f'{M31} {PRAISE} {SINCE} {NR}', pages=5)
add('m31_wins',   f'{M31} {WINS} {SINCE} {NR}', pages=4)
add('m31_neg',    f'{M31} {NEG} {SINCE} {NR}', pages=5)
add('m31_cmp',    f'{M31} {CMP} {SINCE} {NR}', pages=6)
add('m31_price',  f'{M31} {PRICE} {SINCE} {NR}', pages=6)
add('m31_speed',  f'{M31} {SPEED} {SINCE} {NR}', pages=4)
add('m31_chan',   f'{M31} {CHAN} {SINCE} {NR}', pages=6)
add('m31_ident',  f'({M31} OR {SB}) {IDENT} {SINCE} {NR}', pages=4)
add('m31_weights',f'{M31} {WEIGHTS} {SINCE} {NR}', pages=4)
add('m31_trust',  f'{M31} {TRUST} {SINCE} {NR}', pages=3)
add('m31_media',  f'{M31} filter:media {SINCE} {NR}', pages=6)
add('m31_video',  f'{M31} filter:native_video {SINCE} {NR}', pages=3)
add('m31_links',  f'{M31} filter:links -filter:media {SINCE} {NR}', pages=5)
add('m31_minfaves', f'{M31} min_faves:5 {SINCE} {NR}', ('Latest',), 10)
add('m31_replies', f'{M31} filter:replies {SINCE} {NR}', ('Latest',), 6)

# --- C. Space Bunny name today -----------------------------------------------------
add('sb_all_latest', f'{SB} {SINCE} {NR}', ('Latest',), 12)
add('sb_all_top',    f'{SB} {SINCE} {NR}', ('Top',), 5)
add('sb_praise', f'{SB} {PRAISE} {SINCE} {NR}', pages=3)
add('sb_neg',    f'{SB} {NEG} {SINCE} {NR}', pages=3)
add('sb_cmp',    f'{SB} {CMP} {SINCE} {NR}', pages=3)
add('sb_built',  f'{SB} {BUILT} {SINCE} {NR}', pages=3)
add('sb_media',  f'{SB} filter:media {SINCE} {NR}', pages=3)

# --- D. generic MiniMax chatter -----------------------------------------------------
add('mx_flash',  f'{MXF} {SINCE} {NR}', ('Latest','Top'), 6)
add('mx_minimax_latest', f'(minimax OR minimaxagent OR minimax_ai) -hailuo -"video" {SINCE} {NR}', ('Latest',), 12)
add('mx_minimax_top',    f'(minimax OR minimaxagent OR minimax_ai) -hailuo {SINCE} {NR}', ('Top',), 6)
add('mx_code',   f'("minimax code" OR "m plan" OR "token plan") {SINCE} {NR}', ('Latest','Top'), 4)

# --- E. partners / channels (<=11 from: per query) -------------------------------------
P1 = '(from:opencode OR from:cline OR from:OpenRouterAI OR from:OpenRouter OR from:ollama OR from:vercel OR from:kilocode OR from:aisdk OR from:togethercompute OR from:FireworksAI_HQ OR from:basetenco)'
P2 = '(from:novita_labs OR from:ArtificialAnlys OR from:lmarena_ai OR from:zeddotdev OR from:FactoryAI OR from:aihubmix OR from:AntSeed OR from:LMStudioAI OR from:vllm_project OR from:sglproject OR from:huggingface)'
P3 = '(from:GroqInc OR from:CerebrasSystems OR from:nutlope OR from:rauchg OR from:thdxr OR from:cline OR from:saoudrizwan OR from:RooCodeAI OR from:roo_code OR from:continuedev OR from:crush)'
P4 = '(from:scaling01 OR from:swyx OR from:paulgauthier OR from:kimmonismus OR from:testingcatalog OR from:rohanpaul_ai OR from:bindureddy OR from:ArtificialAnlys OR from:lmoroney OR from:simonw OR from:mattshumer_)'
for i,P in enumerate([P1,P2,P3,P4],1):
    add(f'partners{i}', f'{P} (minimax OR "M3.1" OR "space bunny" OR spacebunny OR bunny) since:2026-10-18', ('Latest',), 4)
add('partners_mention', f'(@opencode OR @cline OR @OpenRouterAI OR @ollama OR @vercel OR @kilocode OR @togethercompute OR @AntSeed) ({M31} OR minimax) {SINCE} {NR}', ('Latest',), 6)

# --- F. non-English -----------------------------------------------------------------------
ZHN = '("M3.1" OR "M3.1 Flash" OR "space bunny" OR spacebunny OR 太空兔 OR 太空兔子 OR MiniMax OR 稀宇)'
add('zh_all',  f'{ZHN} -海螺 -视频 lang:zh {SINCE} {NR}', ('Latest','Top'), 8)
add('zh_ang',  f'{ZHN} (做了 OR 一次 OR 实测 OR 成功 OR 惊艳 OR 不错 OR 好用 OR 搞定 OR 修好 OR 体验 OR 对比 OR 评测 OR 便宜 OR 免费 OR 无限 OR 订阅 OR 翻车 OR 拉胯 OR 一般 OR 失望 OR 慢 OR 快 OR 开源 OR 权重 OR 价格 OR 定价) lang:zh {SINCE} {NR}', ('Latest','Top'), 5)
add('ja',      f'("M3.1" OR "space bunny" OR spacebunny OR スペースバニー OR MiniMax) lang:ja {SINCE} {NR}', ('Latest','Top'), 6)
add('ko',      f'("M3.1" OR "space bunny" OR spacebunny OR 스페이스버니 OR 미니맥스 OR MiniMax) lang:ko {SINCE} {NR}', ('Latest','Top'), 3)
add('es_pt',   f'("M3.1" OR "space bunny" OR spacebunny OR MiniMax) (lang:es OR lang:pt) {SINCE} {NR}', ('Latest','Top'), 4)
add('other',   f'("M3.1" OR "space bunny" OR spacebunny OR MiniMax) (lang:fr OR lang:de OR lang:ru OR lang:vi OR lang:id OR lang:tr OR lang:it OR lang:hi OR lang:ar) {SINCE} {NR}', ('Latest','Top'), 4)

def _split_long(limit=470):
    """twitterapi.io returns HTTP 400 for queries longer than ~480 chars: split the angle OR-group."""
    import re
    out=[]
    for q in Q:
        if len(q['query'])<=limit: out.append(q); continue
        m=re.match(r'^(\(.*?\)|\(\(.*?\) OR \(.*?\)\)) \((.*?)\) (since:\S+ -filter:retweets)$', q['query'])
        if not m: out.append(q); print('WARN cannot split', q['tag'], len(q['query'])); continue
        head, angle, tail = m.group(1), m.group(2), m.group(3)
        terms=angle.split(' OR '); chunks=[]; cur=[]
        for t in terms:
            cand=f"{head} ({' OR '.join(cur+[t])}) {tail}"
            if cur and len(cand)>limit: chunks.append(cur); cur=[t]
            else: cur.append(t)
        if cur: chunks.append(cur)
        for i,ch in enumerate(chunks,1):
            out.append(dict(q, tag=f"{q['tag']}_{i}", query=f"{head} ({' OR '.join(ch)}) {tail}"))
    Q[:]=out
_split_long()

def _key():
    for line in (ROOT/'.env').read_text().splitlines():
        if line.startswith('TWITTERAPI_KEY='): return line.split('=',1)[1].strip().strip('"').strip("'")
    raise SystemExit('no key')

def row(t, stamp):
    raw=t.raw
    media=[m.get('type') for m in (raw.get('extendedEntities') or {}).get('media',[]) or []]
    return dict(id=t.id, url=t.url or f'https://x.com/i/status/{t.id}', text=t.text,
                created=t.created_at.isoformat() if t.created_at else None, lang=t.lang,
                author=t.author.handle, author_name=t.author.name, followers=t.author.followers,
                verified=t.author.verified, bio=(t.author.bio or '')[:200],
                likes=t.like_count, retweets=t.retweet_count, replies=t.reply_count,
                quotes=t.quote_count, views=t.view_count, bookmarks=int(raw.get('bookmarkCount') or 0), media=media,
                urls=[u.get('expanded_url') for u in (raw.get('entities',{}) or {}).get('urls',[]) if u.get('expanded_url')],
                in_reply_to=raw.get('inReplyToId'), in_reply_to_user=raw.get('inReplyToUsername'), conversation_id=raw.get('conversationId'),
                quoted_id=(raw.get('quoted_tweet') or {}).get('id'), quoted_text=((raw.get('quoted_tweet') or {}).get('text') or '')[:300],
                matched=[], collected_at=stamp)

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--prefixes', default=''); ap.add_argument('--suffix', default=''); ap.add_argument('--list', action='store_true')
    a=ap.parse_args()
    pref=[x for x in a.prefixes.split(',') if x]
    qs=[q for q in Q if not pref or any(q['tag'].startswith(x) for x in pref)]
    if a.list:
        for q in qs: print(q['tag'], q['modes'], q['max_pages'])
        print(len(qs), 'queries', sum(len(q['modes'])*q['max_pages'] for q in qs), 'max pages'); return
    c = XDataClient(api_key=_key())
    manifest_path = OUT/f'queries{a.suffix}.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    done = {(m['tag'], m['mode']) for m in manifest if m.get('status')=='ok'}
    merged_path = OUT/f'merged{a.suffix}.json'
    seen = {r['id']: r for r in json.loads(merged_path.read_text())} if merged_path.exists() else {}
    for q in qs:
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
