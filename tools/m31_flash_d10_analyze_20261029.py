"""Aggregate classified D+1..D+10 tweets into analysis.json + analysis.md (evidence pack).
Also computes the daily volume curve vs the DeepSeek V4.1-Flash-1017 baseline and the
deltas against the launch-day report (reports/2026-10-19-m31-flash-launch/analysis.json).
Run: .venv/bin/python tools/m31_flash_d10_analyze_20261029.py
"""
from __future__ import annotations
import json, glob, re, collections
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / 'reports/2026-10-29-m31-flash-d10'; E = R / 'evidence'
LAUNCH_REPORT = ROOT / 'reports/2026-10-19-m31-flash-launch/analysis.json'
LAUNCH_EVID = ROOT / 'reports/2026-10-19-m31-flash-launch/evidence'
W0 = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)
FREE_END = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
WEIGHTS = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
OFFICIAL = {'MiniMax_AI', 'MiniMaxAgent', 'Hailuo_AI', 'MiniMax__AI'}
H3_RE = re.compile(r'hailuo|海螺|\bH3\b|video model|text-to-video|image-to-video', re.I)


def load():
    pool = {}
    for f in sorted(glob.glob(str(E / 'merged-*.json'))):
        if f.endswith('merged-baseline.json'):
            continue
        for r in json.loads(Path(f).read_text()):
            old = pool.get(r['id'])
            if old:
                old['matched'] = sorted(set(old['matched']) | set(r['matched']))
            else:
                pool[r['id']] = r
    cls = {c['id']: c for c in json.loads((E / 'classified.json').read_text())}
    rows = []
    for r in pool.values():
        c = cls.get(r['id'], {})
        r = dict(r)
        r.update({k: c.get(k) for k in ('relevant', 'kind', 'first_hand', 'retention', 'days_used',
                                        'task', 'sentiment', 'vs', 'channels', 'topics',
                                        'fix_status', 'claims', 'summary_zh')})
        r['dt'] = datetime.fromisoformat(r['created']) if r.get('created') else None
        rows.append(r)
    return rows


def daily(rows):
    return dict(sorted(collections.Counter(r['dt'].strftime('%m-%d') for r in rows if r['dt']).items()))


def main():
    rows = load()
    total = len(rows)
    rel = [r for r in rows if r['relevant'] and r['dt'] and r['dt'] >= W0]
    rel = [r for r in rel if not (H3_RE.search(r['text']) and not re.search(r'm3\.1|bunny|flash', r['text'], re.I))]
    (E / 'joined.json').write_text(json.dumps([{k: v for k, v in r.items() if k != 'dt'} for r in rel],
                                              ensure_ascii=False, indent=1))
    A = {}
    A['window'] = '2026-10-20T00:00Z .. collection time'
    A['collected_total'] = total
    A['relevant'] = len(rel)
    A['latest_collected'] = max(r['dt'] for r in rows if r['dt']).isoformat()
    nonoff = [r for r in rel if r['author'] not in OFFICIAL]
    fh = [r for r in nonoff if r['first_hand']]
    A['relevant_non_official'] = len(nonoff)
    A['unique_authors'] = len({r['author'] for r in nonoff})
    A['first_hand'] = len(fh)
    A['first_hand_authors'] = len({r['author'] for r in fh})
    A['views_sum_non_official'] = sum(r['views'] or 0 for r in nonoff)
    A['likes_sum_non_official'] = sum(r['likes'] or 0 for r in nonoff)

    # --- volume curve, and the three phases of the window ---------------------------
    A['daily_non_official'] = daily(nonoff)
    A['daily_first_hand'] = daily(fh)
    A['phase_counts'] = {
        'd1_d2_free (10-20..10-21)': sum(1 for r in nonoff if r['dt'] < FREE_END),
        'd3_free_ended (10-22)': sum(1 for r in nonoff if FREE_END <= r['dt'] < WEIGHTS),
        'd4_d10_post_weights (10-23..)': sum(1 for r in nonoff if r['dt'] >= WEIGHTS),
    }

    # --- the retention question ------------------------------------------------------
    A['retention_all'] = dict(collections.Counter(r['retention'] for r in nonoff).most_common())
    A['retention_first_hand'] = dict(collections.Counter(r['retention'] for r in fh).most_common())
    dsu = [r['days_used'] for r in nonoff if isinstance(r.get('days_used'), int)]
    A['days_used_claims'] = dict(sorted(collections.Counter(dsu).items()))

    # --- did the four launch-day complaints get fixed --------------------------------
    A['fix_status'] = dict(collections.Counter(r['fix_status'] for r in nonoff).most_common())
    A['fix_status_by_topic'] = {
        t: dict(collections.Counter(r['fix_status'] for r in nonoff if t in (r['topics'] or [])).most_common())
        for t in ('language_mixing', 'benchmaxx_doubt', 'cache_price', 'thinking_effort')}

    # --- standard cuts ---------------------------------------------------------------
    A['kinds'] = dict(collections.Counter(r['kind'] for r in nonoff).most_common())
    A['kinds_first_hand'] = dict(collections.Counter(r['kind'] for r in fh).most_common())
    A['sentiment_all'] = dict(sorted(collections.Counter(r['sentiment'] for r in nonoff).items(), key=lambda x: str(x[0])))
    A['sentiment_first_hand'] = dict(sorted(collections.Counter(r['sentiment'] for r in fh).items(), key=lambda x: str(x[0])))
    A['tasks_first_hand'] = dict(collections.Counter(r['task'] for r in fh).most_common())
    A['topics'] = dict(collections.Counter(t for r in nonoff for t in (r['topics'] or [])).most_common())
    A['channels'] = dict(collections.Counter(c for r in nonoff for c in (r['channels'] or [])).most_common())
    A['channels_first_hand'] = dict(collections.Counter(c for r in fh for c in (r['channels'] or [])).most_common())
    A['vs'] = dict(collections.Counter(v for r in nonoff for v in (r['vs'] or [])).most_common())
    A['lang'] = dict(collections.Counter(r['lang'] for r in nonoff).most_common())
    A['followers_buckets'] = dict(collections.Counter(
        ('<1k' if (r['followers'] or 0) < 1000 else '1k-10k' if r['followers'] < 10000
         else '10k-100k' if r['followers'] < 100000 else '100k+') for r in nonoff).most_common())
    # sentiment split by follower size and by language, to re-test the launch-day finding
    def sent_split(sub):
        s = [r['sentiment'] for r in sub if isinstance(r.get('sentiment'), int)]
        pos = sum(1 for x in s if x >= 1); neg = sum(1 for x in s if x <= -1)
        return dict(n=len(s), pos=pos, neu=len(s) - pos - neg, neg=neg,
                    pos_pct=round(100 * pos / len(s), 1) if s else None,
                    neg_pct=round(100 * neg / len(s), 1) if s else None)
    A['sentiment_by_followers_first_hand'] = {
        b: sent_split([r for r in fh if b == ('<1k' if (r['followers'] or 0) < 1000 else '1k-10k' if r['followers'] < 10000 else '10k-100k' if r['followers'] < 100000 else '100k+')])
        for b in ('<1k', '1k-10k', '10k-100k', '100k+')}
    A['sentiment_by_lang_first_hand'] = {
        lg: sent_split([r for r in fh if r['lang'] == lg])
        for lg, _ in collections.Counter(r['lang'] for r in fh).most_common(8)}

    # --- DeepSeek baseline, same relative days --------------------------------------
    bl = E / 'merged-baseline.json'
    if bl.exists():
        brs = json.loads(bl.read_text())
        bdt = [datetime.fromisoformat(r['created']) for r in brs if r.get('created')]
        A['baseline_ds_daily'] = dict(sorted(collections.Counter(d.strftime('%m-%d') for d in bdt).items()))
        A['baseline_ds_total'] = len(brs)
        # align by day-offset from each model's own launch (flash 10-19, ds 10-17)
        fl = {int(k[3:]) - 19: v for k, v in A['daily_non_official'].items()}
        ds = {int(k[3:]) - 17: v for k, v in A['baseline_ds_daily'].items()}
        A['volume_vs_baseline_by_day_offset'] = {
            f'D+{d}': dict(flash=fl.get(d), deepseek=ds.get(d),
                           ratio=round(fl[d] / ds[d], 3) if fl.get(d) and ds.get(d) else None)
            for d in range(1, 11)}

    # --- deltas vs the launch-day report --------------------------------------------
    if LAUNCH_REPORT.exists():
        L = json.loads(LAUNCH_REPORT.read_text())
        A['launch_day_reference'] = {k: L.get(k) for k in (
            'relevant', 'relevant_non_official', 'unique_authors', 'first_hand',
            'views_sum_non_official', 'sentiment_first_hand', 'kinds', 'topics', 'channels', 'vs')}
        lv = L.get('views_sum_non_official') or 0
        A['delta_vs_launch_day'] = {
            'non_official_posts': f"{len(nonoff)} vs {L.get('relevant_non_official')}",
            'first_hand_posts': f"{A['first_hand']} vs {L.get('first_hand')}",
            'unique_authors': f"{A['unique_authors']} vs {L.get('unique_authors')}",
            'views': f"{A['views_sum_non_official']} vs {lv}",
            'views_ratio': round(A['views_sum_non_official'] / lv, 3) if lv else None,
        }
        # authors who posted on launch day AND in this window = sustained interest
        lj = LAUNCH_EVID / 'joined.json'
        if lj.exists():
            la = {r['author'] for r in json.loads(lj.read_text()) if r['author'] not in OFFICIAL}
            now_a = {r['author'] for r in nonoff}
            A['author_overlap'] = dict(launch_day=len(la), window=len(now_a),
                                       both=len(la & now_a), new_in_window=len(now_a - la),
                                       retained_pct=round(100 * len(la & now_a) / len(la), 1) if la else None)
            A['returning_authors_sample'] = sorted(la & now_a)[:60]

    def brief(r):
        return dict(id=r['id'], url=f"https://x.com/{r['author']}/status/{r['id']}", author=r['author'],
                    followers=r['followers'], created=(r['created'] or '')[:16], likes=r['likes'],
                    views=r['views'], quotes=r['quotes'], replies=r['replies'], kind=r['kind'],
                    first_hand=r['first_hand'], retention=r['retention'], days_used=r['days_used'],
                    task=r['task'], sentiment=r['sentiment'], fix_status=r['fix_status'], vs=r['vs'],
                    channels=r['channels'], topics=r['topics'], claims=r['claims'],
                    summary_zh=r['summary_zh'], text=r['text'][:600])

    def by_views(sub, n=None):
        s = sorted(sub, key=lambda r: -(r['views'] or 0))
        return [brief(r) for r in (s[:n] if n else s)]

    A['official'] = by_views([r for r in rel if r['author'] in OFFICIAL])
    A['retention_keep'] = by_views([r for r in nonoff if r['kind'] == 'retention_keep' or r['retention'] == 'still_using'])
    A['retention_churn'] = by_views([r for r in nonoff if r['kind'] == 'retention_churn' or r['retention'] == 'switched_away'])
    A['weights_release'] = by_views([r for r in nonoff if r['kind'] == 'weights_release' or 'weights_opensource' in (r['topics'] or [])], 60)
    A['local_deploy'] = by_views([r for r in nonoff if r['kind'] == 'local_deploy' or any(t in (r['topics'] or []) for t in ('local_inference', 'quantization'))], 60)
    A['provider_host'] = by_views([r for r in nonoff if r['kind'] == 'provider_host'], 50)
    A['workshop'] = by_views([r for r in nonoff if r['kind'] == 'workshop_content' or 'workshop' in (r['topics'] or [])], 40)
    A['goodcases'] = by_views([r for r in nonoff if r['kind'] == 'goodcase'])
    A['badcases'] = by_views([r for r in nonoff if r['kind'] == 'badcase'])
    A['still_broken'] = by_views([r for r in nonoff if r['fix_status'] == 'still_broken'], 60)
    A['fixed'] = by_views([r for r in nonoff if r['fix_status'] == 'fixed'], 40)
    A['eval_negative'] = by_views([r for r in nonoff if r['kind'] == 'eval_negative' or (r['sentiment'] or 0) <= -1], 80)
    A['eval_mixed'] = by_views([r for r in nonoff if r['kind'] == 'eval_mixed'], 50)
    A['eval_positive'] = by_views([r for r in nonoff if r['kind'] == 'eval_positive'], 60)
    A['comparisons'] = by_views([r for r in nonoff if r['kind'] == 'comparison' or r['vs']], 80)
    A['pricing'] = by_views([r for r in nonoff if r['kind'] == 'pricing_plan' or any(t in (r['topics'] or []) for t in ('price', 'cache_price', 'free_offer_ended'))], 60)
    A['openrouter_rank'] = by_views([r for r in nonoff if 'openrouter_rank' in (r['topics'] or [])], 30)
    A['speed'] = by_views([r for r in nonoff if r['kind'] == 'speed' or 'speed' in (r['topics'] or [])], 40)
    A['partners'] = by_views([r for r in nonoff if r['kind'] == 'partner_channel'], 50)
    A['bugs'] = by_views([r for r in nonoff if any(t in (r['topics'] or []) for t in ('availability_bugs', 'rate_limit', 'hallucination', 'language_mixing'))], 60)
    A['questions'] = by_views([r for r in nonoff if r['kind'] == 'question'], 40)
    A['non_english'] = by_views([r for r in nonoff if r['lang'] not in ('en', 'und', 'qme', 'zxx')], 60)
    A['big_accounts'] = [brief(r) for r in sorted([r for r in nonoff if (r['followers'] or 0) >= 20000], key=lambda r: -(r['followers'] or 0))[:80]]
    A['top_by_views'] = by_views(nonoff, 40)
    A['top_by_likes'] = [brief(r) for r in sorted(nonoff, key=lambda r: -(r['likes'] or 0))[:40]]

    (R / 'analysis.json').write_text(json.dumps(A, ensure_ascii=False, indent=1, default=str))

    L = []; p = L.append
    p(f"# M3.1 Flash D+1..D+10 retention analysis (window {A['window']}, latest {A['latest_collected']})\n")
    for k in ('collected_total', 'relevant', 'relevant_non_official', 'unique_authors', 'first_hand',
              'first_hand_authors', 'views_sum_non_official', 'likes_sum_non_official'):
        p(f"- {k}: {A[k]}")
    for k in ('daily_non_official', 'daily_first_hand', 'phase_counts', 'retention_all', 'retention_first_hand',
              'days_used_claims', 'fix_status', 'fix_status_by_topic', 'kinds', 'kinds_first_hand',
              'sentiment_all', 'sentiment_first_hand', 'sentiment_by_followers_first_hand',
              'sentiment_by_lang_first_hand', 'tasks_first_hand', 'topics', 'channels',
              'channels_first_hand', 'vs', 'lang', 'followers_buckets', 'baseline_ds_daily',
              'volume_vs_baseline_by_day_offset', 'delta_vs_launch_day', 'author_overlap'):
        if k in A:
            p(f"\n## {k}\n{json.dumps(A[k], ensure_ascii=False)}")

    def sec(title, key, n=None):
        if key not in A:
            return
        p(f"\n## {title} ({len(A[key])})")
        for b in A[key][:n]:
            p(f"- [{b['created']}Z] @{b['author']} ({b['followers']}f) L{b['likes']} V{b['views']} "
              f"{b['kind']}/{b['task']}/s{b['sentiment']} fh={b['first_hand']} ret={b['retention']} "
              f"days={b['days_used']} fix={b['fix_status']} vs={b['vs']} ch={b['channels']} id={b['id']}\n"
              f"  {b['summary_zh']} | claims={b['claims']}\n  > {b['text'][:400].replace(chr(10), ' ')}")
    for t, k in [('Official', 'official'), ('Retention: still using', 'retention_keep'),
                 ('Retention: churned', 'retention_churn'), ('Weights release', 'weights_release'),
                 ('Local deploy', 'local_deploy'), ('Provider hosting', 'provider_host'),
                 ('Workshop / cookbook', 'workshop'), ('Still broken', 'still_broken'), ('Fixed', 'fixed'),
                 ('Good cases', 'goodcases'), ('Bad cases', 'badcases'), ('Negative evals', 'eval_negative'),
                 ('Mixed evals', 'eval_mixed'), ('Positive evals', 'eval_positive'),
                 ('Comparisons', 'comparisons'), ('Pricing / free offer end', 'pricing'),
                 ('OpenRouter rank', 'openrouter_rank'), ('Speed', 'speed'), ('Partners', 'partners'),
                 ('Bugs / availability', 'bugs'), ('Questions', 'questions'), ('Non-English', 'non_english'),
                 ('Big accounts >=20k', 'big_accounts'), ('Top by views', 'top_by_views')]:
        sec(t, k)
    (R / 'analysis.md').write_text('\n'.join(L))
    print('relevant', len(rel), 'non-official', len(nonoff), 'first-hand', A['first_hand'],
          'keep', len(A['retention_keep']), 'churn', len(A['retention_churn']),
          'good', len(A['goodcases']), 'bad', len(A['badcases']))


if __name__ == '__main__':
    main()
