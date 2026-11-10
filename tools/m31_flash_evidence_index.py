"""Build EVIDENCE.md for the two M3.1 Flash reports: every x.com status URL cited in the
reports, resolved against joined.json (author, date, likes, views, kind) + web snapshots list."""
import json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'reports/2026-09-29-m31-flash'
J={j['id']:j for j in json.loads((D/'evidence/joined.json').read_text())}
reports=[p for p in D.glob('REPORT-*.zh-CN.md')]
out=['# 证据索引（M3.1 Flash 双报告）\n']
allids=set()
for rp in reports:
    md=rp.read_text(); ids=re.findall(r'https://x\.com/[^/\s)]+/status/(\d+)', md)
    uniq=list(dict.fromkeys(ids)); allids|=set(uniq)
    out.append(f'## {rp.name}：正文引用 {len(uniq)} 条推文\n')
    out.append('| # | 日期(UTC) | 作者 | 粉丝 | 赞 | 展示 | 分类 | 摘要 | 链接 |\n|---|---|---|---|---|---|---|---|---|')
    for i,tid in enumerate(uniq,1):
        j=J.get(tid)
        if j: out.append(f"| {i} | {(j.get('created') or '')[:16]} | @{j['author']} | {(j.get('followers') or 0):,} | {j.get('likes') or 0} | {(j.get('views') or 0):,} | {j.get('kind')} | {(j.get('summary_zh') or '').replace('|','/')} | [status/{tid}](https://x.com/i/status/{tid}) |")
        else: out.append(f"| {i} | – | – | – | – | – | 未在采样池（来自 9/23–24 报告或人工补查） | | [status/{tid}](https://x.com/i/status/{tid}) |")
    out.append('')
out.append('## 网页快照（reports/2026-09-29-m31-flash/evidence/web/）\n')
for p in sorted((D/'evidence/web').glob('*')):
    out.append(f'- `{p.name}`（{p.stat().st_size:,} bytes）')
qs=[]
for f in ['queries.json','queries-b.json']:
    p=D/'evidence'/f
    if p.exists(): qs+=json.loads(p.read_text())
out.append(f'\n## X 检索清单（{len(qs)} 组查询×通道）\n\n| 标签 | 通道 | 状态 | 条数 | 查询 |\n|---|---|---|---|---|')
for q in qs: out.append(f"| {q['tag']} | {q['mode']} | {q['status']} | {q['count']} | `{q['query'][:160].replace('|','¦')}` |")
(D/'EVIDENCE.md').write_text('\n'.join(out)); print('cited tweets', len(allids), 'queries', len(qs))
