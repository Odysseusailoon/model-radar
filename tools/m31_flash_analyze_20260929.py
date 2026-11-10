"""Aggregate classified M3.1 Flash / Space Bunny tweets into tables for the two reports.
Run: .venv/bin/python tools/m31_flash_analyze_20260929.py  -> reports/2026-09-29-m31-flash/analysis.md + analysis.json
"""
import json, re, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'reports/2026-09-29-m31-flash'
J=json.loads((D/'evidence/joined.json').read_text())
rel=[j for j in J if j.get('relevant')]
def day(j): return (j.get('created') or '')[:10]
def eng(j): return (j.get('likes') or 0)
def link(j): return f"[@{j['author']}]({j['url']})"
C=collections.Counter
out={}
out['total_pool']=len(J); out['relevant']=len(rel)
out['by_kind']=C(j['kind'] for j in rel).most_common()
out['by_task']=C(j['task'] for j in rel).most_common()
out['by_day']=sorted(C(day(j) for j in rel).items())
out['by_lang']=C(j.get('lang') for j in rel).most_common(12)
out['sent_dist']=sorted(C(j.get('sentiment') for j in rel).items(), key=lambda x:str(x[0]))
# first-hand verdicts only
fh=[j for j in rel if j.get('first_hand') and j['kind'] in ('goodcase','eval_positive','eval_negative','eval_mixed','comparison')]
out['firsthand_n']=len(fh)
out['firsthand_sent']=sorted(C(j.get('sentiment') for j in fh).items(), key=lambda x:str(x[0]))
out['firsthand_by_day_sent']={}
for j in fh:
    d=day(j); s=j.get('sentiment') or 0
    b=out['firsthand_by_day_sent'].setdefault(d,{'pos':0,'neg':0,'neu':0,'n':0})
    b['n']+=1; b['pos' if s>0 else 'neg' if s<0 else 'neu']+=1
# task x sentiment for first-hand
tx={}
for j in fh:
    t=j.get('task') or 'none'; s=j.get('sentiment') or 0
    b=tx.setdefault(t,{'pos':0,'neg':0,'neu':0,'n':0,'likes':0}); b['n']+=1; b['likes']+=eng(j); b['pos' if s>0 else 'neg' if s<0 else 'neu']+=1
out['task_sent']=sorted(tx.items(), key=lambda x:-x[1]['n'])
# comparisons
vs=C(); vs_s=collections.defaultdict(lambda:{'pos':0,'neg':0,'neu':0})
for j in rel:
    for v in (j.get('vs') or []):
        vs[v]+=1; s=j.get('sentiment') or 0; vs_s[v]['pos' if s>0 else 'neg' if s<0 else 'neu']+=1
out['vs']=[(v,n,vs_s[v]) for v,n in vs.most_common(25)]
# top lists
def top(kind, n=60, key=None):
    rows=[j for j in rel if (j['kind'] in kind if isinstance(kind,(list,tuple,set)) else j['kind']==kind)]
    rows.sort(key=key or (lambda j:(-eng(j), -(j.get('views') or 0))))
    return rows[:n]
def fmt(j):
    return f"| {day(j)} | {link(j)} ({(j.get('followers') or 0):,}) | {eng(j)} / {(j.get('views') or 0):,} | {j.get('task')} | {j.get('sentiment')} | {(j.get('summary_zh') or '').replace('|','/')} | {'; '.join(j.get('claims') or [])[:220].replace('|','/')} |"
H="| 日期 | 作者(粉丝) | 赞/展示 | 任务 | 情感 | 摘要 | 具体主张 |\n|---|---|---|---|---|---|---|"
md=[f"# analysis dump\n\npool {len(J)} relevant {len(rel)} firsthand {len(fh)}\n"]
md.append("## by_kind\n"+"\n".join(f"- {k}: {n}" for k,n in out['by_kind']))
md.append("## by_task\n"+"\n".join(f"- {k}: {n}" for k,n in out['by_task']))
md.append("## by_day\n"+"\n".join(f"- {k}: {n}" for k,n in out['by_day']))
md.append("## by_lang\n"+"\n".join(f"- {k}: {n}" for k,n in out['by_lang']))
md.append("## firsthand by day\n"+"\n".join(f"- {d}: n={b['n']} pos={b['pos']} neg={b['neg']} neu={b['neu']}" for d,b in sorted(out['firsthand_by_day_sent'].items())))
md.append("## task x sentiment (firsthand)\n"+"\n".join(f"- {t}: n={b['n']} pos={b['pos']} neg={b['neg']} neu={b['neu']} likes={b['likes']}" for t,b in out['task_sent']))
md.append("## vs\n"+"\n".join(f"- {v}: {n} (pos {s['pos']} / neg {s['neg']} / neu {s['neu']})" for v,n,s in out['vs']))
for name,kind,n in [('GOODCASE','goodcase',120),('EVAL_POSITIVE','eval_positive',50),('EVAL_NEGATIVE','eval_negative',60),('EVAL_MIXED','eval_mixed',40),('COMPARISON','comparison',60),('PRICING_PLAN','pricing_plan',50),('IDENTITY','identity',25),('OFFICIAL','official',20),('PARTNER','partner_channel',25),('QUESTION','question',15)]:
    rows=top(kind,n); md.append(f"## {name} ({sum(1 for j in rel if j['kind']==kind)})\n{H}\n"+"\n".join(fmt(j) for j in rows))
# goodcase by task
gc=[j for j in rel if j['kind']=='goodcase']
md.append("## goodcase by task\n"+"\n".join(f"- {t}: {n}" for t,n in C(j.get('task') for j in gc).most_common()))
for t,_ in C(j.get('task') for j in gc).most_common():
    rows=sorted([j for j in gc if j.get('task')==t], key=lambda j:-eng(j))[:25]
    md.append(f"### goodcase/{t}\n{H}\n"+"\n".join(fmt(j) for j in rows))
# non-English relevant
for lg in ['zh','ja','ko','es','pt','fr','de','ru','vi','id','tr']:
    rows=sorted([j for j in rel if j.get('lang')==lg and j['kind'] not in ('news_aggregator','promo_spam')], key=lambda j:-eng(j))[:25]
    if rows: md.append(f"## lang/{lg} ({len(rows)})\n{H}\n"+"\n".join(fmt(j) for j in rows))
# authors
au=collections.defaultdict(lambda:{'n':0,'likes':0,'followers':0,'kinds':C()})
for j in rel:
    a=au[j['author']]; a['n']+=1; a['likes']+=eng(j); a['followers']=max(a['followers'], j.get('followers') or 0); a['kinds'][j['kind']]+=1
top_au=sorted(au.items(), key=lambda x:-x[1]['likes'])[:40]
md.append("## top authors by likes\n| 作者 | 粉丝 | 条数 | 总赞 | 类型 |\n|---|---|---|---|---|\n"+"\n".join(f"| [@{a}](https://x.com/{a}) | {v['followers']:,} | {v['n']} | {v['likes']} | {dict(v['kinds'])} |" for a,v in top_au))
# reach
out['reach']=dict(views=sum(j.get('views') or 0 for j in rel), likes=sum(eng(j) for j in rel), authors=len(au))
md.append(f"## reach\n{out['reach']}")
(D/'analysis.md').write_text("\n\n".join(md)); (D/'analysis.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print('relevant',len(rel),'firsthand',len(fh),'goodcase',len(gc)); print(out['by_kind']); print(out['reach'])
