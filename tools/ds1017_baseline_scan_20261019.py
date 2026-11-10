"""Baseline for volume comparison: DeepSeek-V4.1-Flash-1017 launch (2026-10-17 08:35 UTC), hourly windows 08-22 UTC, Latest, 10 pages each.
Run: TWITTERAPI_MIN_INTERVAL=1.2 .venv/bin/python tools/ds1017_baseline_scan_20261019.py
"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import importlib.util
spec=importlib.util.spec_from_file_location('base', ROOT/'tools/m31_flash_launch_scan_20261019.py'); base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
from app.xclient import XDataClient
OUT=base.OUT; NR='-filter:retweets'
DS='("V4.1 Flash" OR "V4.1-Flash" OR "Flash-1017" OR "Flash 1017" OR "DeepSeek-V4.1" OR "DeepSeek V4.1" OR "deepseek 1017" OR "V4.1-Flash-1017")'
Q=[dict(tag=f'ds_{h:02d}', query=f'{DS} since:2026-10-17_{h:02d}:00:00_UTC until:2026-10-17_{h+1:02d}:00:00_UTC {NR}', modes=['Latest'], max_pages=10) for h in range(8,23)]
c=XDataClient(api_key=base._key())
mp=OUT/'queries-ds.json'; manifest=json.loads(mp.read_text()) if mp.exists() else []
done={(m['tag'],m['mode']) for m in manifest if m.get('status')=='ok'}
mg=OUT/'merged-ds.json'; seen={r['id']:r for r in json.loads(mg.read_text())} if mg.exists() else {}
for q in Q:
    for mode in q['modes']:
        if (q['tag'],mode) in done: continue
        stamp=datetime.now(timezone.utc).isoformat(); rows=[]; status='ok'; err=None
        try:
            for t in c.search_recent(q['query'], query_type=mode, max_pages=q['max_pages']):
                r=seen.setdefault(t.id, base.row(t,stamp)); k=f"{q['tag']}:{mode[0]}"
                if k not in r['matched']: r['matched'].append(k)
                rows.append(t.id)
        except Exception as e: status='error'; err=f'{type(e).__name__}: {e}'[:200]
        manifest.append(dict(tag=q['tag'],mode=mode,query=q['query'],status=status,error=err,count=len(rows),collected_at=stamp))
        mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=1)); mg.write_text(json.dumps(list(seen.values()),ensure_ascii=False,indent=1))
        print(f"{q['tag']}: {status} {len(rows)} total {len(seen)}", flush=True)
print('COMPLETE', len(seen))
