"""Deepen capped hourly windows into 20-minute sub-windows (10 pages each) for DS-1017 (10/17 08-17Z) and M3.1 (10/19 12-14Z)."""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import importlib.util
spec=importlib.util.spec_from_file_location('base', ROOT/'tools/m31_flash_launch_scan_20261019.py'); base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
from app.xclient import XDataClient
OUT=base.OUT; NR='-filter:retweets'
DS='("V4.1 Flash" OR "V4.1-Flash" OR "Flash-1017" OR "Flash 1017" OR "DeepSeek-V4.1" OR "DeepSeek V4.1" OR "deepseek 1017" OR "V4.1-Flash-1017")'
def subs(day,h):
    return [(f'{day}_{h:02d}:00:00_UTC',f'{day}_{h:02d}:20:00_UTC'),(f'{day}_{h:02d}:20:00_UTC',f'{day}_{h:02d}:40:00_UTC'),(f'{day}_{h:02d}:40:00_UTC',f'{day}_{h+1:02d}:00:00_UTC')]
jobs=[('ds','2026-10-17',DS,range(8,17),'merged-ds.json','queries-ds.json'),('win_m31','2026-10-19',base.M31,range(12,14),'merged-w.json','queries-w.json')]
c=XDataClient(api_key=base._key())
for prefix,day,q0,hours,mf,qf in jobs:
    mp=OUT/qf; manifest=json.loads(mp.read_text()); done={(m['tag'],m['mode']) for m in manifest if m.get('status')=='ok'}
    mg=OUT/mf; seen={r['id']:r for r in json.loads(mg.read_text())}
    for h in hours:
        for i,(a,b) in enumerate(subs(day,h)):
            tag=f'{prefix}_{h:02d}_s{i}'
            if (tag,'Latest') in done: continue
            q=f'{q0} since:{a} until:{b} {NR}'; stamp=datetime.now(timezone.utc).isoformat(); rows=[]; status='ok'; err=None
            try:
                for t in c.search_recent(q, query_type='Latest', max_pages=10):
                    r=seen.setdefault(t.id, base.row(t,stamp)); k=f"{tag}:L"
                    if k not in r['matched']: r['matched'].append(k)
                    rows.append(t.id)
            except Exception as e: status='error'; err=f'{type(e).__name__}: {e}'[:200]
            manifest.append(dict(tag=tag,mode='Latest',query=q,status=status,error=err,count=len(rows),collected_at=stamp))
            mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=1)); mg.write_text(json.dumps(list(seen.values()),ensure_ascii=False,indent=1))
            print(f"{tag}: {status} {len(rows)} total {len(seen)}", flush=True)
print('COMPLETE')
