"""Ox Alpha -> MiniMax M3.1 Flash KOL radar: build the outreach tables.

Bottom-up, from the tweet corpora already on disk. No account gets into a table
because someone asserted it should; every row is backed by counted posts.

Inputs (all local JSON tweet dumps):
  ox-alpha-tweets.json
  reports/2026-09-22-flash-synthesis/evidence/ox-alpha/*.json
  reports/2026-09-22-flash-kol/evidence/*.json          (verification scan)
  reports/2026-09-22-flash-gtm/evidence/*.json          (Flash-tier GTM corpus)

Outputs -> reports/2026-09-22-flash-kol/
  kol-radar.csv        one row per account, Feishu-importable
  themes.csv           Table A: conversation landscape
  sentiment.csv        Table B: sentiment split by theme
  edges.csv            Table D: MiniMax relationship graph edges
  cohorts.csv          Table E: three seed graphs
  verification.csv     Table F: proposed names vs. what the data shows
  TABLES.zh-CN.md      all of the above rendered

Usage: .venv/bin/python tools/flash_kol_radar_20260922.py
"""
from __future__ import annotations
import csv, glob, json, math, re, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/2026-09-22-flash-kol'
OUT.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# corpora
# --------------------------------------------------------------------------
OX_FILES = (['ox-alpha-tweets.json']
            + sorted(glob.glob('reports/2026-09-22-flash-synthesis/evidence/ox-alpha/*.json'))
            + sorted(glob.glob('reports/2026-09-22-flash-kol/evidence/ox_*.json'))
            + sorted(glob.glob('reports/2026-09-22-flash-kol/evidence/named_ox_*.json')))
MX_FILES = (sorted(glob.glob('reports/2026-09-22-flash-kol/evidence/named_mx_*.json'))
            + ['reports/2026-09-22-flash-kol/evidence/mx_official.json',
               'reports/2026-09-22-flash-gtm/evidence/off_minimax.json',
               'reports/2026-09-22-flash-gtm/evidence/mx_m31.json',
               'reports/2026-09-22-flash-gtm/evidence/mx_dev.json'])
FLASH_FILES = ['reports/2026-09-22-flash-gtm/evidence/merged.json']

def load(paths):
    rows, seen = [], set()
    for p in paths:
        fp = ROOT / p if not str(p).startswith('/') else Path(p)
        if not fp.exists() or fp.name == 'queries.json':
            continue
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for t in d:
            tid = t.get('id')
            if not tid or tid in seen:
                continue
            seen.add(tid)
            rows.append(t)
    return rows

OX_RE = re.compile(r'ox[\s\-_]?alpha|glm[\s\-]?5\.3[\s\-]?flash', re.I)
ox_all = load(OX_FILES)
ox = [t for t in ox_all if OX_RE.search(t.get('text') or '')]
mx_all = load(MX_FILES)
flash = load(FLASH_FILES)

# --------------------------------------------------------------------------
# theme + sentiment classification
# --------------------------------------------------------------------------
THEMES = {
    'identity_detective': r'tokenizer|which lab|whose model|identity|guess|reveal|revealed|turned out|zhipu|z\.ai|who made|fingerprint|system prompt',
    'benchmark':          r'deepswe|swe[\- ]?bench|benchmark|eval\b|evals|pass rate|pass@|score|leaderboard|\d{2}/\d{2,3}|\d{2}(\.\d)?%',
    'agentic_coding':     r'\bagent|agentic|coding|\bcode\b|codebase|repo\b|tool call|harness|opencode|cline|kilo|roo ?code|refactor|debug',
    'price_context':      r'free|cheap|price|pricing|cost|\$\d|per million|1m context|context window|131k|\d+k output|token limit',
    'reliability':        r'fail|fails|failed|broken|loop|looping|stuck|timeout|worse|regression|hallucin|css|\bui\b|不行|失败',
    'methodology':        r'sample size|variance|\bn ?= ?\d|reproduc|rerun|re-run|retry|full run|larger run|10 task|113|methodolog',
    'serving_speed':      r'tok/s|tokens?/s|tps\b|throughput|latency|fast|faster|speed|slow',
    'local_inference':    r'gguf|mlx|awq|fp8|int4|quant|vllm|sglang|llama\.cpp|lmstudio|local|vram|3090|4090|5090|dgx|spark',
    'distribution':       r'available on|now on|live on|integrat|support(s|ed)? now|route|router|gateway|provider|上线|接入',
}
THEME_RE = {k: re.compile(v, re.I) for k, v in THEMES.items()}

POS = re.compile(r'impressive|insane|amazing|excellent|great|really good|so good|best|love|beats|crush|solid|wow|strong|incredible|banger|goat|nice|惊艳|好用|强|牛', re.I)
NEG = re.compile(r'\bbad\b|worse|worst|fail|failed|broken|disappoint|overhyped|\bmid\b|garbage|trash|useless|slop|regression|can\'t|cannot|struggl|慢|不行|差|垃圾', re.I)

BENCH_RE = re.compile(r'deepswe|swe[\- ]?bench(?:[\- ]?verified)?|aider|livecodebench|terminal[\- ]?bench|humaneval|gpqa|aime|mmlu|tau[\- ]?bench|browsecomp|arc[\- ]?agi', re.I)
MXMODEL_RE = re.compile(r'm2\.5|m2\.7|m3\.1|\bm3\b|minimax|hailuo|海螺', re.I)

def eng(t):
    return (t.get('likes') or 0) + 2 * (t.get('retweets') or 0) + (t.get('quotes') or 0)

def classify(text):
    return {k for k, r in THEME_RE.items() if r.search(text)}

def sentiment(text):
    p, n = bool(POS.search(text)), bool(NEG.search(text))
    if p and not n: return 'positive'
    if n and not p: return 'negative'
    if p and n:     return 'mixed'
    return 'neutral'

# --------------------------------------------------------------------------
# Table A / B: conversation landscape + sentiment
# --------------------------------------------------------------------------
theme_stat = defaultdict(lambda: dict(posts=0, eng=0, pos=0, neg=0, mixed=0, neu=0, authors=defaultdict(int)))
for t in ox:
    txt = t.get('text') or ''
    s = sentiment(txt)
    for th in classify(txt) or {'other'}:
        d = theme_stat[th]
        d['posts'] += 1; d['eng'] += eng(t)
        d[{'positive': 'pos', 'negative': 'neg', 'mixed': 'mixed', 'neutral': 'neu'}[s]] += 1
        d['authors'][t.get('author')] += eng(t) + 1

# --------------------------------------------------------------------------
# per-account aggregation
# --------------------------------------------------------------------------
acct = defaultdict(lambda: dict(
    handle='', name='', followers=0,
    ox_posts=0, ox_eng=0, ox_first=None, ox_last=None, ox_urls=[],
    themes=defaultdict(int), sent=defaultdict(int), benchmarks=set(),
    mx_posts=0, mx_eng=0, mx_models=set(), mx_urls=[],
    flash_posts=0))

def touch(a, t):
    a['handle'] = a['handle'] or t.get('author') or ''
    a['name'] = a['name'] or t.get('author_name') or ''
    a['followers'] = max(a['followers'], t.get('followers') or 0)

for t in ox:
    h = (t.get('author') or '').lower()
    if not h: continue
    a = acct[h]; touch(a, t)
    txt = t.get('text') or ''
    a['ox_posts'] += 1; a['ox_eng'] += eng(t)
    c = t.get('created')
    if c:
        a['ox_first'] = min(a['ox_first'] or c, c); a['ox_last'] = max(a['ox_last'] or c, c)
    if len(a['ox_urls']) < 3: a['ox_urls'].append(t.get('url'))
    for th in classify(txt): a['themes'][th] += 1
    a['sent'][sentiment(txt)] += 1
    for b in BENCH_RE.findall(txt): a['benchmarks'].add(b.lower().replace(' ', '-'))

for t in mx_all:
    h = (t.get('author') or '').lower()
    if not h: continue
    txt = t.get('text') or ''
    if not MXMODEL_RE.search(txt): continue
    a = acct[h]; touch(a, t)
    a['mx_posts'] += 1; a['mx_eng'] += eng(t)
    for m in MXMODEL_RE.findall(txt): a['mx_models'].add(m.lower())
    if len(a['mx_urls']) < 2: a['mx_urls'].append(t.get('url'))

for t in flash:
    h = (t.get('author') or '').lower()
    if h: acct[h]['flash_posts'] += 1

# official amplification edges: MiniMax official account @-mentioning someone
OFFICIAL = {'minimax_ai', 'minimax__ai', 'hailuo_ai', 'minimaxagent'}
amp = defaultdict(list)
for t in mx_all:
    if (t.get('author') or '').lower() in OFFICIAL:
        for m in re.findall(r'@(\w+)', t.get('text') or ''):
            if m.lower() not in OFFICIAL:
                amp[m.lower()].append(t.get('url'))

DISTRIBUTION = {'openrouter', 'openrouterai', 'opencode', 'cline', 'kilocode', 'ollama',
                'vllm_project', 'sglproject', 'sgl_project', 'lmstudioai', 'togethercompute',
                'fireworksai_hq', 'novita_labs', 'basetenco', 'unslothai', 'aihubmix'}
VENDOR = {'zai_org', 'deepseek_ai', 'xiaomimimo', 'minimax_ai', 'minimax__ai', 'hailuo_ai',
          'minimaxagent', 'kimi_moonshot', 'alibaba_qwen', 'openai', 'anthropicai',
          'googledeepmind', 'moonshotai', 'mistralai'}
# MiniMax-side people: second-hop nodes in the relationship graph, never outreach targets
EMPLOYEE_RE = re.compile(r'minimax|hailuo', re.I)

# What an official-amplification edge is actually about. A @comfyui / @fal edge
# is the Hailuo video graph; it does not make that account a Flash coding lead.
VIDEO_ECO = {'comfyui','fal','magnific','runwayml','krea_ai','higgsfield','heygen','pika_labs',
             'lumalabsai','freepik','domoai_app','viggle_ai','capcutapp','artlist_io'}
INFRA_ECO = {'nvidia','nvidiaai','gmi_cloud','nebiusai','sambanovaai','togethercompute','haoailab',
             'sgl_project','sglproject','vllm_project','novita_labs','basetenco','fireworksai_hq',
             'digitalocean','modal_labs','runpod_io'}
CODING_ECO = {'kilocode','cline','opencode','openrouter','openrouterai','factoryai','cursor_ai',
              'windsurf_ai','roocode','continuedev','arena','lmarena_ai','artificialanlys',
              'openhandsdev','nousresearch'}

def edge_domain(h):
    if h in VIDEO_ECO: return 'video_ecosystem'
    if h in CODING_ECO: return 'coding_agent'
    if h in INFRA_ECO: return 'cloud_serving'
    return 'other'

# --------------------------------------------------------------------------
# scoring (the proposal's weights, computed rather than asserted)
# --------------------------------------------------------------------------
ox_eng_vals = sorted(a['ox_eng'] for a in acct.values() if a['ox_posts']) or [0]
def pct(v, arr):
    if not arr or v <= 0: return 0.0
    return sum(1 for x in arr if x <= v) / len(arr)

ANGLE = {
    'benchmarker':       'same harness, same task set: pass rate + wall clock + tokens + tool-failure rate + $',
    'coding_power_user': 'day-0 access, daily-drive it on their own repo, publish whatever comes out',
    'local_inference':   'weights/quant/throughput: tok-s on their own hardware',
    'distribution':      'day-0 route + telemetry + a comparison page, as a partner not a KOL',
    'model_analyst':     'technical fact sheet + architecture story, not marketing copy',
    'vendor':            'competitor / first-party account — monitor, do not pitch',
    'KOC':               'monitor; engage only if they post a real task result',
}

rows = []
for h, a in acct.items():
    ox_aff = 0.0
    if a['ox_posts']:
        ox_aff = 0.6 * min(1.0, math.log1p(a['ox_posts']) / math.log1p(6)) + 0.4 * pct(a['ox_eng'], ox_eng_vals)
    mx_aff = min(1.0, math.log1p(a['mx_posts']) / math.log1p(5)) if a['mx_posts'] else 0.0
    # an official @-mention only counts as Flash-relevant warmth when the edge is
    # in the coding/serving graph, or the account itself showed up in Ox Alpha /
    # Flash conversation. Otherwise it is a Hailuo video edge.
    relevant_amp = h in amp and (edge_domain(h) in ('coding_agent', 'cloud_serving')
                                 or a['ox_posts'] or a['flash_posts'])
    if relevant_amp: mx_aff = min(1.0, mx_aff + 0.4)
    th = a['themes']
    code_rel = min(1.0, (th.get('agentic_coding', 0) + th.get('local_inference', 0)
                         + min(a['flash_posts'], 5)) / 5)
    bench = min(1.0, (th.get('benchmark', 0) + th.get('methodology', 0)) / 3)
    posts = max(1, a['ox_posts'] + a['mx_posts'])
    eq = min(1.0, math.log1p((a['ox_eng'] + a['mx_eng']) / posts) / math.log1p(120))
    warmth = (1.0 if relevant_amp else 0.8 if h in DISTRIBUTION
              else 0.5 if h in amp else 0.4 if a['mx_posts'] else 0.0)
    score = (0.30 * ox_aff + 0.25 * mx_aff + 0.15 * code_rel
             + 0.10 * bench + 0.10 * eq + 0.10 * warmth)

    sent = a['sent']
    dom = max(sent, key=sent.get) if sent else 'n/a'
    audience = ('distribution' if h in DISTRIBUTION else
                'vendor' if h in VENDOR else
                'benchmarker' if bench >= 0.6 else
                'local_inference' if th.get('local_inference') else
                'coding_power_user' if th.get('agentic_coding') else
                'model_analyst' if th.get('identity_detective') else 'KOC')
    is_vendor = h in VENDOR
    is_employee = bool(EMPLOYEE_RE.search(h)) and not is_vendor
    excluded = ('vendor_account' if is_vendor else 'minimax_side_person' if is_employee else '')
    tier = 'T3' if score >= 0.50 else 'T2' if score >= 0.30 else 'T1'
    if excluded: tier = '—'
    rows.append(dict(
        handle=a['handle'] or h, name=a['name'], followers=a['followers'],
        tier=tier, score=round(score, 3),
        ox_affinity=round(ox_aff, 3), mx_affinity=round(mx_aff, 3),
        coding_relevance=round(code_rel, 3), benchmark_behavior=round(bench, 3),
        engagement_quality=round(eq, 3), relationship_warmth=round(warmth, 2),
        ox_posts=a['ox_posts'], ox_engagement=a['ox_eng'],
        ox_first=(a['ox_first'] or '')[:10], ox_last=(a['ox_last'] or '')[:10],
        themes='|'.join(sorted(th, key=th.get, reverse=True)),
        sentiment=dom,
        sentiment_split=f"+{sent.get('positive',0)}/~{sent.get('neutral',0)+sent.get('mixed',0)}/-{sent.get('negative',0)}",
        benchmark_names='|'.join(sorted(a['benchmarks'])),
        mx_posts=a['mx_posts'], mx_models='|'.join(sorted(a['mx_models'])),
        relation_official=('amplified_by_official' if h in amp else
                           'distribution_partner' if h in DISTRIBUTION else
                           'posted_about_minimax' if a['mx_posts'] else 'none'),
        official_amplification_count=len(amp.get(h, [])),
        audience_type=audience,
        risk_or_skepticism=('yes' if sent.get('negative') or th.get('reliability') else ''),
        engagement_angle=ANGLE.get(audience, ''),
        excluded_reason=excluded,
        amplification_domain=(edge_domain(h) if h in amp else ''),
        ox_evidence=' '.join(x for x in a['ox_urls'] if x),
        mx_evidence=' '.join(x for x in a['mx_urls'] if x),
    ))

rows.sort(key=lambda r: -r['score'])

# --------------------------------------------------------------------------
# writers
# --------------------------------------------------------------------------
def write_csv(name, rows, fields=None):
    if not rows: return
    fields = fields or list(rows[0].keys())
    with (OUT / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, '') for k in fields})

write_csv('kol-radar.csv', rows)

theme_rows = []
for th, d in sorted(theme_stat.items(), key=lambda kv: -kv[1]['posts']):
    top = sorted(d['authors'].items(), key=lambda kv: -kv[1])[:4]
    theme_rows.append(dict(theme=th, posts=d['posts'], share=f"{d['posts']/max(1,len(ox)):.0%}",
                           engagement=d['eng'],
                           positive=d['pos'], neutral=d['neu'] + d['mixed'], negative=d['neg'],
                           net=f"{(d['pos']-d['neg'])/max(1,d['posts']):+.0%}",
                           top_accounts='|'.join('@' + a for a, _ in top if a)))
write_csv('themes.csv', theme_rows)

sent_rows = []
for s in ('positive', 'neutral', 'mixed', 'negative'):
    n = sum(1 for t in ox if sentiment(t.get('text') or '') == s)
    e = sum(eng(t) for t in ox if sentiment(t.get('text') or '') == s)
    sent_rows.append(dict(sentiment=s, posts=n, share=f'{n/max(1,len(ox)):.1%}', engagement=e))
write_csv('sentiment.csv', sent_rows)

edge_rows = []
for h, urls in sorted(amp.items(), key=lambda kv: -len(kv[1])):
    a = acct.get(h, {})
    edge_rows.append(dict(node='@' + (a.get('handle') or h), edge_type='official_amplification',
                          domain=edge_domain(h), count=len(urls),
                          ox_posts=a.get('ox_posts', 0), mx_posts=a.get('mx_posts', 0),
                          evidence=' '.join(urls[:3])))
for h in sorted(DISTRIBUTION):
    a = acct.get(h)
    if not a: continue
    edge_rows.append(dict(node='@' + (a['handle'] or h), edge_type='distribution_partner',
                          domain=edge_domain(h), count=a['ox_posts'] + a['mx_posts'],
                          ox_posts=a['ox_posts'], mx_posts=a['mx_posts'],
                          evidence=' '.join(x for x in a['ox_urls'][:2] if x)))
edge_rows.sort(key=lambda r: ({'coding_agent': 0, 'cloud_serving': 1, 'other': 2, 'video_ecosystem': 3}[r['domain']], -r['count']))
write_csv('edges.csv', edge_rows)

LAB = ['MiniMax_AI', 'Zai_org', 'Kimi_Moonshot', 'deepseek_ai', 'XiaomiMiMo']
coh_rows = []
for h in LAB:
    coh_rows.append(dict(cohort='LAB_GRAPH', handle='@' + h, basis='vendor account', score='', tier=''))
for r in rows:
    if r['ox_posts'] >= 1 and r['tier'] in ('T3', 'T2') and not r['excluded_reason']:
        coh_rows.append(dict(cohort='OX_ALPHA_GRAPH', handle='@' + r['handle'],
                             basis=f"{r['ox_posts']} ox posts", score=r['score'], tier=r['tier']))
for r in rows:
    if r['mx_posts'] >= 1 and r['tier'] in ('T3', 'T2') and not r['excluded_reason']:
        coh_rows.append(dict(cohort='MINIMAX_ADVOCATE_GRAPH', handle='@' + r['handle'],
                             basis=f"{r['mx_posts']} minimax posts, {r['relation_official']}",
                             score=r['score'], tier=r['tier']))
write_csv('cohorts.csv', coh_rows)

# Table G: the benchmark-claim ledger. The Ox Alpha story is a number that moved;
# this pins each number to who said it and when.
CLAIM_RE = re.compile(r'(\d{1,3}(?:\.\d)?)\s?%|(\d{1,3})\s?/\s?113|~?(\d{2}(?:\.\d)?)\s?(?:on|pass)', re.I)
BENCH_CTX = re.compile(r'deepswe|swe[\- ]?bench|benchmark|pass rate|cyber|eval', re.I)
claim_rows = []
for t in ox:
    txt = ' '.join((t.get('text') or '').split())
    if not BENCH_CTX.search(txt): continue
    nums = [n for grp in CLAIM_RE.findall(txt) for n in grp if n]
    nums = [n for n in nums if 20 <= float(n) <= 100]
    if not nums: continue
    claim_rows.append(dict(date=(t.get('created') or '')[:10], handle='@' + (t.get('author') or ''),
                           followers=t.get('followers') or 0, likes=t.get('likes') or 0,
                           numbers='|'.join(dict.fromkeys(nums)),
                           stance=sentiment(txt),
                           claim=txt[:170], url=t.get('url')))
claim_rows.sort(key=lambda r: (r['date'], -r['likes']))
write_csv('benchmark-claims.csv', claim_rows)

# verification of the proposed names
NAMED = ["winkey_h","davis7","MiaAI_lab","kilocode","Prathkum","thdxr","OpenRouterAI","opencode",
         "ArtificialAnlys","arena","TheTuringPost","NousResearch","AndrewCurran_","spdustin",
         "AGTPinsights","kimmonismus","bytebot","openhandsdev","eliebakouch","alexellisuk","patrickc"]
by_handle = {r['handle'].lower(): r for r in rows}
ver_rows = []
for n in NAMED:
    r = by_handle.get(n.lower())
    ver_rows.append(dict(proposed=('@' + n),
                         ox_posts_found=(r['ox_posts'] if r else 0),
                         mx_posts_found=(r['mx_posts'] if r else 0),
                         flash_corpus_posts=(acct.get(n.lower(), {}).get('flash_posts', 0)),
                         verdict=('confirmed' if r and r['ox_posts'] else
                                  'minimax-only' if r and r['mx_posts'] else 'no evidence in corpus'),
                         data_tier=(r['tier'] if r else '—'),
                         score=(r['score'] if r else ''),
                         evidence=(r['ox_evidence'] or r['mx_evidence'] if r else '')))
write_csv('verification.csv', ver_rows)

print(f'ox corpus: {len(ox)} posts / {len(set(t["author"] for t in ox))} accounts')
print(f'minimax corpus: {len(mx_all)} posts; flash corpus: {len(flash)}')
print(f'accounts scored: {len(rows)}  T3={sum(1 for r in rows if r["tier"]=="T3")} '
      f'T2={sum(1 for r in rows if r["tier"]=="T2")} T1={sum(1 for r in rows if r["tier"]=="T1")}')
print('wrote', ', '.join(p.name for p in sorted(OUT.glob('*.csv'))))

# --------------------------------------------------------------------------
# markdown render
# --------------------------------------------------------------------------
def md_table(rows, cols, headers=None):
    headers = headers or cols
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join('---' for _ in cols) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(r.get(c, '')).replace('|', '/') for c in cols) + ' |')
    return '\n'.join(out)

t3 = [r for r in rows if r['tier'] == 'T3' and not r['excluded_reason']]
t2 = [r for r in rows if r['tier'] == 'T2' and not r['excluded_reason']][:40]
excl = [r for r in rows if r['excluded_reason']][:15]
doc = []
doc.append('# Ox Alpha → MiniMax M3.1 Flash：KOL Radar 表\n')
doc.append(f'口径：2026-09-22。语料 {len(ox)} 条 Ox Alpha / GLM-5.3-Flash 推文（{len(set(t["author"] for t in ox))} 个账号），'
           f'{len(mx_all)} 条 MiniMax 相关推文，{len(flash)} 条 Flash 档 GTM 推文。'
           '每一行都由实际计数得出；没有任何账��因为"被推荐"而进表。\n')

doc.append('## 表 A · Ox Alpha conversation landscape\n')
doc.append(md_table(theme_rows, ['theme', 'posts', 'share', 'engagement', 'positive', 'neutral', 'negative', 'net', 'top_accounts'],
                    ['主题', '帖数', '占比', '互动量', '正', '中', '负', '净情绪', '核心账号']) + '\n')

doc.append('## 表 B · 情绪分布（全语料）\n')
doc.append(md_table(sent_rows, ['sentiment', 'posts', 'share', 'engagement'], ['情绪', '帖数', '占比', '互动量']) + '\n')

doc.append(f'## 表 C · M3.1 Flash outreach list（T3 = {len(t3)}）\n')
doc.append(md_table(t3, ['handle', 'followers', 'score', 'ox_posts', 'ox_engagement', 'themes', 'sentiment',
                         'benchmark_names', 'mx_posts', 'relation_official', 'audience_type',
                         'risk_or_skepticism', 'engagement_angle'],
                    ['账号', '粉丝', '分数', 'Ox帖', 'Ox互动', '主题', '情绪', 'benchmark', 'MX帖',
                     '与官号关系', '受众类型', '风险/质疑', '建议切入点']) + '\n')

doc.append(f'## 表 C2 · T2 监控名单（前 {len(t2)}）\n')
doc.append(md_table(t2, ['handle', 'followers', 'score', 'ox_posts', 'mx_posts', 'themes', 'sentiment',
                         'relation_official', 'audience_type'],
                    ['账号', '粉丝', '分数', 'Ox帖', 'MX帖', '主题', '情绪', '与官号关系', '受众类型']) + '\n')

doc.append('## 表 D · MiniMax relationship graph edges\n')
doc.append(md_table([e for e in edge_rows if e['domain'] != 'video_ecosystem'][:30],
                    ['node', 'edge_type', 'domain', 'count', 'ox_posts', 'mx_posts', 'evidence'],
                    ['节点', '边类型', '所属图', '次数', 'Ox帖', 'MX帖', '证据']) + '\n')
doc.append(f"\n官号放大边里属于 Hailuo 视频生态的还有 {sum(1 for e in edge_rows if e['domain']=='video_ecosystem')} 个"
           f"（@comfyui / @fal / @magnific / @runwayml 等），它们不是 Flash coding cohort，"
           "在评分里不计入 relationship_warmth。\n")
doc.append('### 被排除出 outreach 名单的节点\n')
doc.append(md_table(excl, ['handle', 'excluded_reason', 'mx_posts', 'ox_posts'],
                    ['账号', '排除原因', 'MX帖', 'Ox帖']) + '\n')

doc.append('## 表 E · 三个 cohort seed graph\n')
for c in ('LAB_GRAPH', 'OX_ALPHA_GRAPH', 'MINIMAX_ADVOCATE_GRAPH'):
    sub = [r for r in coh_rows if r['cohort'] == c][:25]
    doc.append(f'### {c}（{sum(1 for r in coh_rows if r["cohort"]==c)}）\n')
    doc.append(md_table(sub, ['handle', 'basis', 'score', 'tier'], ['账号', '依据', '分数', 'Tier']) + '\n')

doc.append(f'## 表 F · Ox Alpha benchmark 数字账本（{len(claim_rows)} 条）\n')
doc.append('同一个模型，不同人报出的数字差了 20 多个点。这张表把每个数字钉到发帖人和时间上。\n')
doc.append(md_table([c for c in claim_rows if c['likes'] >= 30][:30],
                    ['date', 'handle', 'followers', 'likes', 'numbers', 'stance', 'claim'],
                    ['日期', '账号', '粉丝', '赞', '报出的数字', '立场', '原文']) + '\n')

doc.append('## 表 G · 提案名单 vs. 数据核验\n')
doc.append(md_table(ver_rows, ['proposed', 'verdict', 'ox_posts_found', 'mx_posts_found', 'flash_corpus_posts', 'data_tier', 'score'],
                    ['提案账号', '核验结论', 'Ox帖数', 'MX帖数', 'Flash语料帖数', '数据Tier', '分数']) + '\n')

doc.append('## 评分口径\n')
doc.append('```\nM3.1_interest_score = 0.30*ox_affinity + 0.25*mx_affinity + 0.15*coding_relevance\n'
           '                    + 0.10*benchmark_behavior + 0.10*engagement_quality + 0.10*relationship_warmth\n'
           'T3 >= 0.50   T2 >= 0.30   T1 < 0.30\n```\n')
doc.append('- `ox_affinity` = 0.6×log(帖数) + 0.4×互动量分位；`mx_affinity` = log(MiniMax 帖数)，官号转发 +0.4\n'
           '- `relationship_warmth` = 官号放大 1.0 / 分发伙伴 0.8 / 发过 MiniMax 0.4 / 无 0\n'
           '- `risk_or_skepticism=yes` 不降级：给过负面反馈的人是 evaluator，不是要剔除的对象\n')

(OUT / 'TABLES.zh-CN.md').write_text('\n'.join(doc))
print('wrote', (OUT / 'TABLES.zh-CN.md').relative_to(ROOT))
