"""Batch-tag M3.1 Flash / Space Bunny tweets with Claude via aihubmix gateway.
Merges new scan (reports/2026-09-29-m31-flash/evidence/merged.json) with the
2026-09-23/24 Space Bunny scans, dedupes, classifies in batches of 12, resumable.
Run: .venv/bin/python tools/m31_flash_classify_20260929.py
"""
from __future__ import annotations
import json, re, sys, time, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
E = ROOT/'reports/2026-09-29-m31-flash/evidence'
OUT = E/'classified.json'
PRIOR = ['spacebunny-goodcase-2026-09-23.json','spacebunny-dimension-2026-09-24.json','spacebunny-frontend-2026-09-24.json','spacebunny-tweets-2026-09-23-r2.json','spacebunny-tweets-2026-09-23.json']

def env(k):
    for line in (ROOT/'.env').read_text().splitlines():
        if line.startswith(k+'='): return line.split('=',1)[1].strip().strip('"').strip("'")
import anthropic
import os
client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY') or env('ANTHROPIC_API_KEY'), base_url=os.environ.get('ANTHROPIC_BASE_URL') or env('ANTHROPIC_BASE_URL'), timeout=120, max_retries=3)
MODEL = os.environ.get('ANTHROPIC_DEFAULT_HAIKU_MODEL') or 'claude-haiku-4-5'

SYSTEM = """You tag tweets about MiniMax's model "M3.1-Flash-Preview" (official launch 2026-09-27 on MiniMax Code / Token Plan), which ran as the stealth model "Space Bunny Alpha" on OpenRouter/OpenCode from 2026-09-23. Treat Space Bunny Alpha and M3.1 Flash as the same product.
For EACH tweet return a JSON object with:
- id: string (copy)
- relevant: true only if the tweet is substantively about this model (M3.1 / Space Bunny) — its behavior, output, price/plan, identity, or a comparison including it. Lists of many free models, generic AI news digests that merely mention it in passing, and unrelated "M3.1"/"space bunny" (e.g. Apple M3, games, songs) are relevant=false.
- kind: one of goodcase | eval_positive | eval_negative | eval_mixed | comparison | pricing_plan | identity | official | partner_channel | news_aggregator | promo_spam | question | other
  goodcase = author describes a concrete thing they had the model do AND the outcome was good (built X, fixed Y, ran N subagents...).
  eval_* = an opinion/verdict about the model without a concrete artifact, or with a negative/mixed outcome.
  comparison = puts it against named other models. pricing_plan = about price, Token Plan / M Plan, unlimited week, check-in credits, free access. identity = speculation that Space Bunny == MiniMax. official = MiniMax accounts. partner_channel = OpenRouter/OpenCode/Cline/Kilo etc announcing availability. news_aggregator = newsletter/digest style. promo_spam = affiliate/engagement bait.
- first_hand: true if author personally used it (vs. relaying).
- task: one of frontend_web | game | graphics_3d | agentic_workflow | debugging | refactor_migration | backend_data | long_context | multimodal_vision | writing_nontech | tool_calling | reasoning_math | speed_latency | cost | general | none
- sentiment: integer -2..2 toward the model (0 = neutral/no verdict).
- vs: list of other model names explicitly compared against (normalize: "Sonnet 5.5", "GPT-6 Sol", "Gemini 3.8 Flash", "GLM-5.3-Flash", "DeepSeek-V4.1-Flash", "MiMo-V2.6-Flash", "Kimi K3", "Qwen", "Grok", "Opus", "Fable" ...), else [].
- claims: up to 3 short concrete claims in English (numbers, durations, artifacts, failure modes). [] if none.
- summary_zh: one Chinese sentence (<=40 chars) of what the tweet says.
Output ONLY a JSON array, same order as input, no prose."""

def load():
    pool={}
    for f in PRIOR:
        p=ROOT/f
        if not p.exists(): continue
        for r in json.loads(p.read_text()):
            r=dict(r); r.setdefault('provenance',f); r.setdefault('matched',[])
            pool.setdefault(r['id'], r)
    new=[]
    for f in ('merged.json','merged-b.json'):
        if (E/f).exists(): new+=json.loads((E/f).read_text())
    for r in new:
        old=pool.get(r['id'])
        if old: old['matched']=sorted(set(old.get('matched',[]))|set(r.get('matched',[]))); old.update({k:v for k,v in r.items() if k not in ('matched','provenance')}); old['provenance']=old.get('provenance','')+'|new'
        else: r['provenance']='new'; pool[r['id']]=r
    return pool

def batch_call(items):
    payload=[dict(id=i['id'], author=i['author'], followers=i.get('followers'), lang=i.get('lang'), created=(i.get('created') or '')[:16], likes=i.get('likes'), views=i.get('views'), in_reply=bool(i.get('in_reply_to')), text=i['text'][:1200]) for i in items]
    for attempt in range(3):
        try:
            m=client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM, messages=[{"role":"user","content":json.dumps(payload, ensure_ascii=False)}])
            txt=''.join(b.text for b in m.content if getattr(b,'type',None)=='text')
            s=txt.find('['); e=txt.rfind(']')
            arr=json.loads(txt[s:e+1])
            if len(arr)!=len(items): raise ValueError(f'len {len(arr)}!={len(items)}')
            return arr
        except Exception as ex:
            print('  retry', attempt, type(ex).__name__, str(ex)[:120], flush=True); time.sleep(2+attempt*3)
    return [dict(id=i['id'], relevant=None, kind='error') for i in items]

def main():
    pool=load()
    done={}
    if OUT.exists():
        for r in json.loads(OUT.read_text()):
            if r.get('kind')!='error': done[r['id']]=r
    todo=[r for r in pool.values() if r['id'] not in done]
    print('pool',len(pool),'done',len(done),'todo',len(todo), flush=True)
    todo.sort(key=lambda r:-(r.get('likes') or 0))
    batches=[todo[i:i+12] for i in range(0,len(todo),12)]
    results=dict(done)
    def work(b):
        return b, batch_call(b)
    n=0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for b,arr in ex.map(work, batches):
            for item,tag in zip(b,arr):
                tag=dict(tag); tag['id']=item['id']
                results[item['id']]=tag
            n+=1
            if n%5==0 or n==len(batches):
                OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=0))
                print(f'batch {n}/{len(batches)} tagged {len(results)}', flush=True)
    OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=0))
    # merge tags into a joined file for analysis
    joined=[]
    for pid,r in pool.items():
        t=results.get(pid,{})
        j=dict(r); j.pop('raw',None); j.update({k:t.get(k) for k in ('relevant','kind','first_hand','task','sentiment','vs','claims','summary_zh')})
        joined.append(j)
    (E/'joined.json').write_text(json.dumps(joined, ensure_ascii=False, indent=0))
    from collections import Counter
    rel=[j for j in joined if j.get('relevant')]
    print('relevant',len(rel)); print(Counter(j['kind'] for j in rel).most_common()); print(Counter(j['task'] for j in rel).most_common())
if __name__=='__main__': main()
