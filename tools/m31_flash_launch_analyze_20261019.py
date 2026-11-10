"""Aggregate classified launch-day tweets into analysis.json + analysis.md (human-readable evidence pack).
Run: .venv/bin/python tools/m31_flash_launch_analyze_20261019.py
"""
from __future__ import annotations
import json, glob, re, collections
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
R = ROOT/'reports/2026-10-19-m31-flash-launch'; E = R/'evidence'
LAUNCH = datetime(2026,10,19,11,56,tzinfo=timezone.utc); TEASER = datetime(2026,10,19,9,21,tzinfo=timezone.utc)
OFFICIAL = {'MiniMax_AI','MiniMaxAgent','Hailuo_AI','MiniMax__AI'}
H3_RE = re.compile(r'hailuo|海螺|\bH3\b|video model|text-to-video|image-to-video', re.I)

def load():
    pool={}
    for f in sorted(glob.glob(str(E/'merged-*.json'))):
        if f.endswith('merged-ds.json'): continue
        for r in json.loads(Path(f).read_text()):
            old=pool.get(r['id'])
            if old: old['matched']=sorted(set(old['matched'])|set(r['matched']))
            else: pool[r['id']]=r
    cls={c['id']:c for c in json.loads((E/'classified.json').read_text())}
    rows=[]
    for r in pool.values():
        c=cls.get(r['id'],{})
        r=dict(r); r.update({k:c.get(k) for k in ('relevant','kind','first_hand','task','sentiment','vs','channels','topics','claims','summary_zh')})
        r['dt']=datetime.fromisoformat(r['created']) if r.get('created') else None
        rows.append(r)
    return rows

def main():
    rows=load()
    total=len(rows)
    rel=[r for r in rows if r['relevant'] and r['dt'] and r['dt']>=datetime(2026,10,19,8,0,tzinfo=timezone.utc)]
    # drop MiniMax video-model noise unless it also names M3.1/bunny
    rel=[r for r in rel if not (H3_RE.search(r['text']) and not re.search(r'm3\.1|bunny|flash', r['text'], re.I))]
    (E/'joined.json').write_text(json.dumps([{k:v for k,v in r.items() if k!='dt'} for r in rel], ensure_ascii=False, indent=1))
    A={}
    A['collected_total']=total; A['relevant']=len(rel)
    A['latest_collected']=max(r['dt'] for r in rows if r['dt']).isoformat()
    nonoff=[r for r in rel if r['author'] not in OFFICIAL]
    A['relevant_non_official']=len(nonoff)
    A['unique_authors']=len({r['author'] for r in nonoff})
    A['first_hand']=sum(1 for r in nonoff if r['first_hand'])
    A['first_hand_authors']=len({r['author'] for r in nonoff if r['first_hand']})
    # hourly volume (UTC)
    hv=collections.Counter(r['dt'].strftime('%H') for r in nonoff)
    A['hourly_utc']=dict(sorted(hv.items()))
    A['pre_teaser']=sum(1 for r in nonoff if r['dt']<TEASER); A['teaser_to_launch']=sum(1 for r in nonoff if TEASER<=r['dt']<LAUNCH); A['post_launch']=sum(1 for r in nonoff if r['dt']>=LAUNCH)
    # kinds / sentiment / tasks / topics / channels / vs / lang
    A['kinds']=dict(collections.Counter(r['kind'] for r in nonoff).most_common())
    A['sentiment_all']=dict(sorted(collections.Counter(r['sentiment'] for r in nonoff).items(), key=lambda x: str(x[0])))
    fh=[r for r in nonoff if r['first_hand']]
    A['sentiment_first_hand']=dict(sorted(collections.Counter(r['sentiment'] for r in fh).items(), key=lambda x: str(x[0])))
    A['kinds_first_hand']=dict(collections.Counter(r['kind'] for r in fh).most_common())
    A['tasks_first_hand']=dict(collections.Counter(r['task'] for r in fh).most_common())
    A['topics']=dict(collections.Counter(t for r in nonoff for t in (r['topics'] or [])).most_common())
    A['channels']=dict(collections.Counter(c for r in nonoff for c in (r['channels'] or [])).most_common())
    A['channels_first_hand']=dict(collections.Counter(c for r in fh for c in (r['channels'] or [])).most_common())
    A['vs']=dict(collections.Counter(v for r in nonoff for v in (r['vs'] or [])).most_common())
    A['lang']=dict(collections.Counter(r['lang'] for r in nonoff).most_common())
    A['views_sum_non_official']=sum(r['views'] or 0 for r in nonoff); A['likes_sum_non_official']=sum(r['likes'] or 0 for r in nonoff)
    A['followers_buckets']=dict(collections.Counter(('<1k' if (r['followers'] or 0)<1000 else '1k-10k' if r['followers']<10000 else '10k-100k' if r['followers']<100000 else '100k+') for r in nonoff).most_common())
    # top posts by views / likes
    def brief(r): return dict(id=r['id'], url=f"https://x.com/{r['author']}/status/{r['id']}", author=r['author'], followers=r['followers'], created=r['created'][11:16], likes=r['likes'], views=r['views'], quotes=r['quotes'], replies=r['replies'], kind=r['kind'], first_hand=r['first_hand'], task=r['task'], sentiment=r['sentiment'], vs=r['vs'], channels=r['channels'], topics=r['topics'], claims=r['claims'], summary_zh=r['summary_zh'], text=r['text'][:600])
    A['top_by_views']=[brief(r) for r in sorted(nonoff, key=lambda r:-(r['views'] or 0))[:40]]
    A['top_by_likes']=[brief(r) for r in sorted(nonoff, key=lambda r:-(r['likes'] or 0))[:40]]
    A['goodcases']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='goodcase'], key=lambda r:-(r['views'] or 0))]
    A['badcases']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='badcase'], key=lambda r:-(r['views'] or 0))]
    A['eval_negative']=[brief(r) for r in sorted([r for r in nonoff if r['kind'] in ('eval_negative',) or (r['sentiment'] or 0)<=-1], key=lambda r:-(r['views'] or 0))]
    A['eval_mixed']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='eval_mixed'], key=lambda r:-(r['views'] or 0))]
    A['eval_positive']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='eval_positive'], key=lambda r:-(r['views'] or 0))[:60]]
    A['comparisons']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='comparison' or r['vs']], key=lambda r:-(r['views'] or 0))[:80]]
    A['partners']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='partner_channel'], key=lambda r:-(r['views'] or 0))]
    A['official']=[brief(r) for r in sorted([r for r in rel if r['author'] in OFFICIAL], key=lambda r:-(r['views'] or 0))]
    A['pricing']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='pricing_plan' or 'price' in (r['topics'] or [])], key=lambda r:-(r['views'] or 0))[:60]]
    A['speed']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='speed' or 'speed' in (r['topics'] or [])], key=lambda r:-(r['views'] or 0))[:40]]
    A['identity']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='identity_reveal' or 'identity_reveal' in (r['topics'] or [])], key=lambda r:-(r['views'] or 0))[:50]]
    A['weights']=[brief(r) for r in sorted([r for r in nonoff if 'weights_opensource' in (r['topics'] or [])], key=lambda r:-(r['views'] or 0))[:40]]
    A['trust']=[brief(r) for r in sorted([r for r in nonoff if 'trust_china' in (r['topics'] or [])], key=lambda r:-(r['views'] or 0))[:30]]
    A['bugs']=[brief(r) for r in sorted([r for r in nonoff if any(t in (r['topics'] or []) for t in ('availability_bugs','rate_limit','hallucination'))], key=lambda r:-(r['views'] or 0))[:60]]
    A['questions']=[brief(r) for r in sorted([r for r in nonoff if r['kind']=='question'], key=lambda r:-(r['views'] or 0))[:40]]
    A['non_english']=[brief(r) for r in sorted([r for r in nonoff if r['lang'] not in ('en','und','qme','zxx')], key=lambda r:-(r['views'] or 0))[:60]]
    A['big_accounts']=[brief(r) for r in sorted([r for r in nonoff if (r['followers'] or 0)>=20000], key=lambda r:-(r['followers'] or 0))[:80]]
    (R/'analysis.json').write_text(json.dumps(A, ensure_ascii=False, indent=1, default=str))
    # markdown
    L=[]; p=L.append
    p(f"# M3.1 Flash launch-day X analysis (collected up to {A['latest_collected']})\n")
    for k in ['collected_total','relevant','relevant_non_official','unique_authors','first_hand','first_hand_authors','pre_teaser','teaser_to_launch','post_launch','views_sum_non_official','likes_sum_non_official']: p(f"- {k}: {A[k]}")
    for k in ['hourly_utc','kinds','kinds_first_hand','sentiment_all','sentiment_first_hand','tasks_first_hand','topics','channels','channels_first_hand','vs','lang','followers_buckets']: p(f"\n## {k}\n{json.dumps(A[k], ensure_ascii=False)}")
    def sec(title, key, n=None):
        p(f"\n## {title} ({len(A[key])})")
        for b in A[key][:n]:
            p(f"- [{b['created']}Z] @{b['author']} ({b['followers']}f) L{b['likes']} V{b['views']} {b['kind']}/{b['task']}/s{b['sentiment']} fh={b['first_hand']} vs={b['vs']} ch={b['channels']} id={b['id']}\n  {b['summary_zh']} | claims={b['claims']}\n  > {b['text'][:400].replace(chr(10),' ')}")
    for t,k in [('Official','official'),('Partners','partners'),('Top by views','top_by_views'),('Good cases','goodcases'),('Bad cases','badcases'),('Negative evals','eval_negative'),('Mixed evals','eval_mixed'),('Positive evals','eval_positive'),('Comparisons','comparisons'),('Pricing','pricing'),('Speed','speed'),('Identity reveal','identity'),('Weights/open-source','weights'),('Trust/China','trust'),('Bugs/availability','bugs'),('Questions','questions'),('Non-English','non_english'),('Big accounts >=20k','big_accounts')]:
        sec(t,k)
    (R/'analysis.md').write_text('\n'.join(L))
    print('relevant',len(rel),'non-official',len(nonoff),'first-hand',A['first_hand'],'good',len(A['goodcases']),'bad',len(A['badcases']))
if __name__=='__main__': main()
