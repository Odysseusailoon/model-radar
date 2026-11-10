"""MiniMax M3.1 Flash — D+1..D+10 retention scan (window 2026-10-20 .. 2026-10-29).

Different question from the launch-day report (reports/2026-10-19-m31-flash-launch/):
launch day = volume + first impression; D+10 = who is STILL using it, and what the
first-week complaints turned into.

Window anchors:
  10/19 11:56 UTC  public launch
  10/22            72h free period ends      -> churn / "still worth it" signal
  10/23            open weights released     -> HF downloads, quants, local, vLLM/SGLang
  10/28            Fireworks x MiniMax Flash workshop
Known launch-day negatives to re-test: Japanese language mixing, benchmaxx accusations,
5x cache price, thinking not disableable (default max).

Run:
  TWITTERAPI_MIN_INTERVAL=1.2 .venv/bin/python tools/m31_flash_d10_scan_20261029.py --group main --suffix -a
  TWITTERAPI_MIN_INTERVAL=1.2 .venv/bin/python tools/m31_flash_d10_scan_20261029.py --group windows
  TWITTERAPI_MIN_INTERVAL=1.2 .venv/bin/python tools/m31_flash_d10_scan_20261029.py --group baseline
"""
from __future__ import annotations
import json, re, sys, importlib.util
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('base', ROOT / 'tools/m31_flash_launch_scan_20261019.py')
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
from app.xclient import XDataClient

OUT = ROOT / 'reports/2026-10-29-m31-flash-d10/evidence'
OUT.mkdir(parents=True, exist_ok=True)

M31, SB, NR = base.M31, base.SB, '-filter:retweets'
MXF = base.MXF
SINCE = 'since:2026-10-20_00:00:00_UTC'          # launch day itself already covered by 10/19 run
UNTIL = 'until:2026-10-29_23:59:59_UTC'
W = f'{SINCE} {UNTIL}'

# --- angle vocabularies: reuse launch-day ones so counts stay same-caliber ---------
BUILT, FIXED, AGENT = base.BUILT, base.FIXED, base.AGENT
LONG, MM, PRAISE = base.LONG, base.MM, base.PRAISE
WINS, NEG, CMP = base.WINS, base.NEG, base.CMP
PRICE, SPEED, CHAN = base.PRICE, base.SPEED, base.CHAN
WEIGHTS, TRUST = base.WEIGHTS, base.TRUST

# --- new D+10-only angles ----------------------------------------------------------
RETAIN = '("still using" OR "still use" OR "been using" OR "using it for" OR "daily driver" OR "daily-driver" OR "switched to" OR "switched from" OR "replaced" OR "replacing" OR "moved to" OR "moved off" OR "went back" OR "going back" OR "gave up" OR "dropped it" OR "stopped using" OR "cancelled" OR "canceled" OR "unsubscribed" OR "resubscribed" OR "renewed" OR "a week" OR "one week" OR "few days" OR "all week" OR "since launch" OR "after a week")'
FREE   = '("free" OR "free tier" OR "free period" OR "free trial" OR "trial ended" OR "promo" OR "promotion" OR "expired" OR "now paying" OR "paying for" OR "worth it" OR "not worth" OR "credits" OR "ran out" OR "72h" OR "72 hours" OR "3 days")'
LOCAL  = '("llama.cpp" OR llamacpp OR gguf OR mlx OR exllama OR "lm studio" OR lmstudio OR ollama OR vllm OR sglang OR "4bit" OR "8bit" OR awq OR fp8 OR quant OR quantized OR quantization OR "run it locally" OR "running locally" OR "local" OR "on my mac" OR "m3 ultra" OR "3090" OR "4090" OR "5090" OR h100 OR a100 OR "two gpus" OR vram)'
HOST   = '(fireworks OR together OR togetherai OR baseten OR novita OR deepinfra OR parasail OR nebius OR siliconflow OR hyperbolic OR replicate OR groq OR cerebras OR sambanova OR "on openrouter" OR provider OR providers OR "serving" OR "now live on" OR "available on" OR endpoint OR "api access")'
WORKSHOP = '(workshop OR webinar OR meetup OR "live stream" OR livestream OR "office hours" OR tutorial OR cookbook OR "how to" OR guide OR notebook OR colab OR recipe OR "fine-tune" OR finetune OR "fine tune" OR lora OR distill)'
FIXCHK = '(japanese OR 日本語 OR "mixed language" OR "language mixing" OR "mixing languages" OR chinese characters OR "random chinese" OR "thinking" OR "reasoning" OR "turn off" OR "disable" OR "non-thinking" OR "no thinking" OR "cache" OR "caching" OR "cached" OR "prompt cache" OR "cache price" OR "cache pricing" OR benchmaxx OR benchmaxxed OR "benchmark maxing" OR contaminated OR contamination OR "trained on" OR "fixed" OR "patched" OR "update" OR "updated")'
RANK   = '("openrouter" OR "token share" OR "tokens/week" OR "weekly tokens" OR leaderboard OR ranking OR rankings OR "top 10" OR "#1" OR trending OR "market share" OR usage OR adoption OR downloads OR "hugging face" OR huggingface OR stars)'
EVAL   = '("artificial analysis" OR artificialanlys OR "aider" OR "polyglot" OR "swe-bench" OR "swe bench" OR "terminal-bench" OR "terminal bench" OR "livebench" OR "lmarena" OR arena OR elo OR "independent" OR "third party" OR "my eval" OR "my benchmark" OR "ran the" OR "scored" OR "score" OR results)'

Q = []
def add(tag, query, modes=('Latest', 'Top'), pages=3):
    Q.append(dict(tag=tag, query=query, modes=list(modes), max_pages=pages))

# ================= group: main ====================================================
MAIN = []
def addm(*a, **k):
    n = len(Q); add(*a, **k); MAIN.extend(q['tag'] for q in Q[n:])

# A. official + replies in the window (post-launch follow-ups, fixes, announcements)
addm('off_all', '(from:MiniMaxAgent OR from:MiniMax_AI OR from:Hailuo_AI OR from:MiniMax__AI) ' + W, ('Latest',), 8)
addm('to_off', f'(to:MiniMaxAgent OR to:MiniMax_AI) {W} {NR}', ('Latest',), 10)

# B. the retention question
addm('retain',   f'{M31} {RETAIN} {W} {NR}', pages=6)
addm('retain_mx',f'{MXF} {RETAIN} {W} {NR}', pages=4)
addm('free_end', f'{M31} {FREE} {W} {NR}', pages=5)
addm('rank',     f'{M31} {RANK} {W} {NR}', pages=5)

# C. open weights (10/23) -> local + third-party hosting
addm('weights',  f'{M31} {WEIGHTS} {W} {NR}', pages=6)
addm('local',    f'{M31} {LOCAL} {W} {NR}', pages=6)
addm('host',     f'{M31} {HOST} {W} {NR}', pages=6)
addm('workshop', f'({M31} OR {MXF}) {WORKSHOP} {W} {NR}', pages=4)
addm('fireworks',f'(fireworks OR FireworksAI_HQ OR from:FireworksAI_HQ) (minimax OR "M3.1" OR flash) {W} {NR}', ('Latest','Top'), 5)

# D. did the four launch-day complaints get fixed / did they stick
addm('fixchk',   f'{M31} {FIXCHK} {W} {NR}', pages=6)
addm('neg',      f'{M31} {NEG} {W} {NR}', pages=6)
addm('ja_neg',   f'("M3.1" OR "minimax" OR スペースバニー) lang:ja {W} {NR}', ('Latest','Top'), 6)

# E. sustained real usage (the "real feedback" the launch day could not show)
addm('built',    f'{M31} {BUILT} {W} {NR}', pages=6)
addm('fixed_by', f'{M31} {FIXED} {W} {NR}', pages=5)
addm('agent',    f'{M31} {AGENT} {W} {NR}', pages=6)
addm('long',     f'{M31} {LONG} {W} {NR}', pages=4)
addm('mm',       f'{M31} {MM} {W} {NR}', pages=3)
addm('praise',   f'{M31} {PRAISE} {W} {NR}', pages=5)
addm('wins',     f'{M31} {WINS} {W} {NR}', pages=4)
addm('eval',     f'{M31} {EVAL} {W} {NR}', pages=6)
addm('cmp',      f'{M31} {CMP} {W} {NR}', pages=7)
addm('price',    f'{M31} {PRICE} {W} {NR}', pages=6)
addm('speed',    f'{M31} {SPEED} {W} {NR}', pages=4)
addm('chan',     f'{M31} {CHAN} {W} {NR}', pages=6)
addm('trust',    f'{M31} {TRUST} {W} {NR}', pages=3)

# F. wide nets
addm('m31_all',   f'{M31} {W} {NR}', ('Latest',), 20)
addm('m31_top',   f'{M31} {W} {NR}', ('Top',), 8)
addm('m31_faves', f'{M31} min_faves:5 {W} {NR}', ('Latest',), 12)
addm('m31_media', f'{M31} filter:media {W} {NR}', ('Latest',), 6)
addm('m31_links', f'{M31} filter:links -filter:media {W} {NR}', ('Latest',), 5)
addm('mx_wide',   f'(minimax OR minimaxagent OR minimax_ai) -hailuo {W} {NR}', ('Latest',), 14)
addm('mx_flash',  f'{MXF} {W} {NR}', ('Latest','Top'), 6)
addm('sb_all',    f'{SB} {W} {NR}', ('Latest',), 6)

# G. partners / non-English (same account sets as launch day, so deltas are comparable)
for i, P in enumerate([base.P1, base.P2, base.P3, base.P4], 1):
    addm(f'partners{i}', f'{P} (minimax OR "M3.1" OR "space bunny" OR spacebunny) {W}', ('Latest',), 5)
ZHN = '("M3.1" OR "M3.1 Flash" OR 太空兔 OR MiniMax OR 稀宇)'
addm('zh_all', f'{ZHN} -海螺 -视频 lang:zh {W} {NR}', ('Latest','Top'), 8)
addm('zh_ang', f'{ZHN} (还在用 OR 退了 OR 换回 OR 开源 OR 权重 OR 部署 OR 本地 OR 量化 OR 涨价 OR 免费 OR 实测 OR 对比 OR 评测 OR 翻车 OR 好用 OR 不好用) lang:zh {W} {NR}', ('Latest','Top'), 5)
addm('ko_es_pt', f'("M3.1" OR spacebunny OR MiniMax) (lang:ko OR lang:es OR lang:pt) {W} {NR}', ('Latest','Top'), 4)
addm('other_lang', f'("M3.1" OR spacebunny OR MiniMax) (lang:fr OR lang:de OR lang:ru OR lang:vi OR lang:id OR lang:tr OR lang:it OR lang:hi OR lang:ar) {W} {NR}', ('Latest','Top'), 4)

# ================= group: windows (daily volume, not capped by 400-row pagination) ==
WINDOWS = []
for d in range(20, 30):
    w = f'since:2026-10-{d:02d}_00:00:00_UTC until:2026-10-{d+1:02d}_00:00:00_UTC'
    for tag, q, pg in (
        (f'win_m31_{d:02d}', f'{M31} {w} {NR}', 10),
        (f'win_mx_{d:02d}', f'(minimax OR minimaxagent OR minimax_ai) -hailuo {w} {NR}', 8),
    ):
        add(tag, q, ('Latest',), pg); WINDOWS.append(tag)

# ================= group: baseline (DeepSeek 1017, same relative D+1..D+10) =========
BASELINE = []
# same term set as tools/ds1017_baseline_scan_20261019.py so D+10 volume is same-caliber
DS = '("V4.1 Flash" OR "V4.1-Flash" OR "Flash-1017" OR "Flash 1017" OR "DeepSeek-V4.1" OR "DeepSeek V4.1" OR "deepseek 1017" OR "V4.1-Flash-1017")'
for d in range(18, 28):
    w = f'since:2026-10-{d:02d}_00:00:00_UTC until:2026-10-{d+1:02d}_00:00:00_UTC'
    tag = f'base_ds_{d:02d}'
    add(tag, f'{DS} {w} {NR} lang:en', ('Latest',), 10); BASELINE.append(tag)
add('base_ds_retain', f'{DS} {RETAIN} since:2026-10-18_00:00:00_UTC until:2026-10-28_00:00:00_UTC {NR}', ('Latest',), 6)
BASELINE.append('base_ds_retain')

GROUPS = {'main': MAIN, 'windows': WINDOWS, 'baseline': BASELINE}

def _split_long(limit=470):
    """twitterapi.io returns HTTP 400 over ~480 chars. base._split_long()'s regex only
    handles a bare `since:... -filter:retweets` tail, so re-implement for `since until`."""
    out = []
    for q in Q:
        if len(q['query']) <= limit:
            out.append(q); continue
        m = re.match(r'^(\(.*?\)|\(\(.*?\) OR \(.*?\)\)) \((.*?)\) (since:\S+(?: until:\S+)?(?: \S+)*)$', q['query'])
        if not m:
            out.append(q); print('WARN cannot split', q['tag'], len(q['query'])); continue
        head, angle, tail = m.group(1), m.group(2), m.group(3)
        chunks, cur = [], []
        for t in angle.split(' OR '):
            cand = f"{head} ({' OR '.join(cur + [t])}) {tail}"
            if cur and len(cand) > limit:
                chunks.append(cur); cur = [t]
            else:
                cur.append(t)
        if cur:
            chunks.append(cur)
        for i, ch in enumerate(chunks, 1):
            out.append(dict(q, tag=f"{q['tag']}_{i}", query=f"{head} ({' OR '.join(ch)}) {tail}"))
    Q[:] = out


_split_long()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--group', default='main', choices=sorted(GROUPS) + ['all'])
    ap.add_argument('--suffix', default='')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    want = set(GROUPS[a.group]) if a.group != 'all' else None
    qs = [q for q in Q if want is None or q['tag'].split('_')[0] in {t.split('_')[0] for t in want}
          or q['tag'] in want or any(q['tag'].startswith(t + '_') for t in want)]
    if a.list:
        for q in qs:
            print(q['tag'], q['modes'], q['max_pages'], len(q['query']))
        print(len(qs), 'queries', sum(len(q['modes']) * q['max_pages'] for q in qs), 'max pages')
        return
    c = XDataClient(api_key=base._key())
    sfx = a.suffix or f'-{a.group}'
    mp = OUT / f'queries{sfx}.json'
    manifest = json.loads(mp.read_text()) if mp.exists() else []
    done = {(m['tag'], m['mode']) for m in manifest if m.get('status') == 'ok'}
    mg = OUT / f'merged{sfx}.json'
    seen = {r['id']: r for r in json.loads(mg.read_text())} if mg.exists() else {}
    for q in qs:
        for mode in q['modes']:
            if (q['tag'], mode) in done:
                continue
            stamp = datetime.now(timezone.utc).isoformat(); rows = []; status = 'ok'; err = None
            try:
                for t in c.search_recent(q['query'], query_type=mode, max_pages=q['max_pages']):
                    r = seen.setdefault(t.id, base.row(t, stamp))
                    k = f"{q['tag']}:{mode[0]}"
                    if k not in r['matched']:
                        r['matched'].append(k)
                    rows.append(t.id)
            except Exception as e:
                status = 'error'; err = f'{type(e).__name__}: {e}'[:200]
            manifest.append(dict(tag=q['tag'], mode=mode, query=q['query'], status=status,
                                 error=err, count=len(rows), collected_at=stamp))
            mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
            mg.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1))
            print(f"{q['tag']}/{mode}: {status} {len(rows)} total {len(seen)}", flush=True)
    print('COMPLETE', len(seen), flush=True)


if __name__ == '__main__':
    main()
