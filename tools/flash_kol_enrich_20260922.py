"""Enrich the T3/T2 rows of kol-radar.csv via twitterapi.io (user/info +
check_follow_relationship vs @MiniMax_AI), the same way the 2026-08-01
候选人 table was built. Resumable: enrich-cache.json is keyed by handle.

Run:
    .venv/bin/python tools/flash_kol_enrich_20260922.py
"""
import csv, json, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'reports/2026-09-22-flash-kol'
CACHE = D / 'enrich-cache.json'
OUT = D / 'kol-enriched.csv'
TARGET = 'MiniMax_AI'
INTERVAL = 2.0
API = 'https://api.twitterapi.io/twitter/user'

key = None
for line in (ROOT / '.env').read_text().splitlines():
    if line.startswith('TWITTERAPI_KEY='):
        key = line.split('=', 1)[1].strip().strip('"').strip("'")
if not key:
    raise SystemExit('TWITTERAPI_KEY missing')
H = {'X-API-Key': key}

def get(path, params):
    for attempt in range(4):
        try:
            r = httpx.get(f'{API}/{path}', params=params, headers=H, timeout=25.0)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(INTERVAL * (2 ** attempt)); continue
            d = r.json()
            if d.get('status') == 'success':
                return d.get('data') or {}
            return None
        except Exception:
            time.sleep(INTERVAL * (2 ** attempt))
    return None

rows = [r for r in csv.DictReader(open(D / 'kol-radar.csv'))
        if r['tier'] in ('T3', 'T2') and not r['excluded_reason']]
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
todo = [r['handle'] for r in rows if r['handle'] not in cache]
print(f'rows {len(rows)}  cached {len(cache)}  todo {len(todo)}', flush=True)

last = 0.0
def throttle():
    global last
    w = INTERVAL - (time.monotonic() - last)
    if w > 0: time.sleep(w)
    last = time.monotonic()

for n, h in enumerate(todo, 1):
    throttle(); u = get('info', {'userName': h}) or {}
    throttle(); f = get('check_follow_relationship',
                        {'source_user_name': h, 'target_user_name': TARGET})
    cache[h] = {
        'name': u.get('name'), 'bio': u.get('description'),
        'followers': u.get('followers'), 'following': u.get('following'),
        'statuses': u.get('statusesCount'), 'created': u.get('createdAt'),
        'verified': u.get('isBlueVerified'), 'location': u.get('location'),
        'user_ok': bool(u),
        'follows_minimax': None if f is None else bool(f.get('following')),
        'minimax_follows': None if f is None else bool(f.get('followed_by')),
    }
    if n % 10 == 0 or n == len(todo):
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        print(f'progress {n}/{len(todo)}', flush=True)
CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

def rel(c):
    a, b = c.get('follows_minimax'), c.get('minimax_follows')
    if a is None or b is None: return '未知'
    if a and b: return '互粉'
    if a: return 'TA关注MiniMax'
    if b: return 'MiniMax关注TA'
    return '无关系'

def seen(r):
    ox, mx = int(float(r['ox_posts'] or 0)), int(float(r['mx_posts'] or 0))
    return 'Ox Alpha + MiniMax' if ox and mx else 'Ox Alpha' if ox else 'MiniMax'

with open(OUT, 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['handle', 'name', 'bio', 'followers', 'following', 'X链接', 'personas', 'seen_via',
                '关注MiniMax', 'MiniMax关注TA', '关系', 'tier', 'score', 'ox_posts', 'mx_posts',
                'sentiment', 'risk_or_skepticism', 'engagement_angle', 'location', 'created',
                'verified', 'ox_evidence', 'mx_evidence'])
    for r in rows:
        c = cache.get(r['handle'], {})
        w.writerow([r['handle'], c.get('name') or r['name'], c.get('bio') or '',
                    c.get('followers') or r['followers'], c.get('following') or '',
                    f"https://x.com/{r['handle']}", r['audience_type'], seen(r),
                    {True: '已关注', False: '未关注'}.get(c.get('follows_minimax'), '未知'),
                    {True: '已关注', False: '未关注'}.get(c.get('minimax_follows'), '未知'),
                    rel(c), r['tier'], r['score'], r['ox_posts'], r['mx_posts'], r['sentiment'],
                    r['risk_or_skepticism'], r['engagement_angle'], c.get('location') or '',
                    (c.get('created') or '')[:10], c.get('verified') or '',
                    r['ox_evidence'], r['mx_evidence']])
n_f = sum(1 for c in cache.values() if c.get('follows_minimax'))
n_b = sum(1 for c in cache.values() if c.get('minimax_follows'))
print(f'wrote {OUT}  follows_minimax={n_f}  minimax_follows={n_b}', flush=True)
print('COMPLETE', flush=True)
