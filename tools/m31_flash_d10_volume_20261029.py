"""Uncapped volume curve: 4-hour UTC windows for M3.1 Flash and the DeepSeek V4.1-Flash-1017
baseline over the SAME calendar days, queried in the same pass so retrieval depth is equal.

Why: daily windows (tools/m31_flash_d10_scan_20261029.py --group windows|baseline) returned
exactly 200/160 for most days = the twitterapi Latest pagination ceiling (20 pages x 20).
Those counts are caps, not volume. 4h windows with max_pages=20 (400 ceiling) clear it.

Run: TWITTERAPI_MIN_INTERVAL=1.8 .venv/bin/python tools/m31_flash_d10_volume_20261029.py
"""
import sys, json, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('base', ROOT / 'tools/m31_flash_launch_scan_20261019.py')
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
from app.xclient import XDataClient

OUT = ROOT / 'reports/2026-10-29-m31-flash-d10/evidence'
NR = '-filter:retweets'
M31 = base.M31
DS = '("V4.1 Flash" OR "V4.1-Flash" OR "Flash-1017" OR "Flash 1017" OR "DeepSeek-V4.1" OR "DeepSeek V4.1" OR "deepseek 1017" OR "V4.1-Flash-1017")'

Q = []
d0 = datetime(2026, 10, 20, tzinfo=timezone.utc)
for day in range(10):
    for h in range(0, 24, 4):
        a = d0 + timedelta(days=day, hours=h); b = a + timedelta(hours=4)
        if a >= datetime(2026, 10, 29, 2, tzinfo=timezone.utc):
            continue
        w = f"since:{a.strftime('%Y-%m-%d_%H:%M:%S')}_UTC until:{b.strftime('%Y-%m-%d_%H:%M:%S')}_UTC"
        s = a.strftime('%m%d_%H')
        Q.append(dict(tag=f'v_flash_{s}', query=f'{M31} {w} {NR}', max_pages=20))
        Q.append(dict(tag=f'v_ds_{s}', query=f'{DS} {w} {NR}', max_pages=20))

c = XDataClient(api_key=base._key())
mp = OUT / 'queries-vol.json'; manifest = json.loads(mp.read_text()) if mp.exists() else []
done = {m['tag'] for m in manifest if m.get('status') == 'ok'}
mg = OUT / 'merged-vol.json'; seen = {r['id']: r for r in json.loads(mg.read_text())} if mg.exists() else {}
for q in Q:
    if q['tag'] in done:
        continue
    stamp = datetime.now(timezone.utc).isoformat(); rows = []; status = 'ok'; err = None
    try:
        for t in c.search_recent(q['query'], query_type='Latest', max_pages=q['max_pages']):
            r = seen.setdefault(t.id, base.row(t, stamp))
            if q['tag'] not in r['matched']:
                r['matched'].append(q['tag'])
            rows.append(t.id)
    except Exception as e:
        status = 'error'; err = f'{type(e).__name__}: {e}'[:200]
    manifest.append(dict(tag=q['tag'], query=q['query'], status=status, error=err,
                         count=len(rows), capped=(len(rows) >= 400), collected_at=stamp))
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    mg.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1))
    print(f"{q['tag']}: {status} {len(rows)}{' CAPPED' if len(rows)>=400 else ''} total {len(seen)}", flush=True)
print('COMPLETE', len(seen), flush=True)
