"""Build the uncapped daily volume curve for M3.1 Flash vs DeepSeek V4.1-Flash-1017
from the 4-hour-window scan (merged-vol.json), and write volume.json + a markdown table.
Run: .venv/bin/python tools/m31_flash_d10_volume_agg_20261029.py
"""
import json, collections
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / 'reports/2026-10-29-m31-flash-d10'; E = R / 'evidence'
OFFICIAL = {'MiniMax_AI', 'MiniMaxAgent', 'Hailuo_AI', 'MiniMax__AI',
            'deepseek_ai', 'DeepSeek_AI', 'deepseekai'}

rows = json.loads((E / 'merged-vol.json').read_text())
man = json.loads((E / 'queries-vol.json').read_text())
ok = {m['tag'] for m in man if m['status'] == 'ok'}
missing = sorted({m['tag'] for m in man} - ok)

flash, ds = collections.Counter(), collections.Counter()
fa, da = collections.defaultdict(set), collections.defaultdict(set)
for r in rows:
    if not r.get('created'):
        continue
    day = r['created'][:10]
    tags = [t for t in r['matched'] if t in ok]
    isf = any(t.startswith('v_flash_') for t in tags)
    isd = any(t.startswith('v_ds_') for t in tags)
    if r['author'] in OFFICIAL:
        continue
    if isf:
        flash[day] += 1; fa[day].add(r['author'])
    if isd:
        ds[day] += 1; da[day].add(r['author'])

days = sorted(set(flash) | set(ds))
out = {'missing_windows': missing, 'note': '4h windows, max_pages=20 (400 ceiling); no window hit the ceiling',
       'daily': {}}
L = ['| 日期 | Flash 条 | Flash 作者 | DeepSeek 条 | DS 作者 | Flash/DS |',
     '|---|---|---|---|---|---|']
for d in days:
    f, s = flash[d], ds[d]
    ratio = f'{f/s:.2f}x' if s else '—'
    out['daily'][d] = dict(flash=f, flash_authors=len(fa[d]), deepseek=s, deepseek_authors=len(da[d]),
                           ratio=round(f / s, 3) if s else None)
    L.append(f'| {d} | {f} | {len(fa[d])} | {s} | {len(da[d])} | {ratio} |')
tf, td = sum(flash.values()), sum(ds.values())
out['total'] = dict(flash=tf, deepseek=td, ratio=round(tf / td, 3) if td else None)
L.append(f'| **合计** | **{tf}** | | **{td}** | | **{tf/td:.2f}x** |' if td else '')
(R / 'volume.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
(R / 'volume-table.md').write_text('\n'.join(L))
print('\n'.join(L))
print()
print('missing windows:', len(missing), missing[:8])
