"""Batch-tag M3.1 Flash launch-day (2026-10-19) tweets with Claude Haiku (12/batch, 6 threads, resumable).
Reads reports/2026-10-19-m31-flash-launch/evidence/merged-*.json, writes classified.json.
Run: .venv/bin/python tools/m31_flash_launch_classify_20261019.py   (uses shell ANTHROPIC_API_KEY/BASE_URL)
"""
from __future__ import annotations
import json, os, sys, time, glob, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
E = ROOT/'reports/2026-10-19-m31-flash-launch/evidence'
OUT = E/'classified.json'
import anthropic
def env(k):
    for line in (ROOT/'.env').read_text().splitlines():
        if line.startswith(k+'='): return line.split('=',1)[1].strip().strip('"').strip("'")
client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY') or env('ANTHROPIC_API_KEY'), base_url=os.environ.get('ANTHROPIC_BASE_URL') or env('ANTHROPIC_BASE_URL'), timeout=120, max_retries=3)
MODEL = os.environ.get('ANTHROPIC_DEFAULT_HAIKU_MODEL') or 'claude-haiku-4-5'

SYSTEM = """You tag tweets collected on 2026-10-19, the public launch day of MiniMax's model "M3.1 Flash" (MiniMax-M3.1-Flash). Facts: teaser 09:21 UTC "Welcome back. Space Bunny"; launch 11:56 UTC. MiniMax confirmed the stealth model "Space Bunny (Alpha)" (free on OpenRouter/OpenCode since 2026-09-23, #1 by tokens there) was an earlier build of M3.1 Flash. Official claims: 1/3 cost and 3x speed of M3; API $0.15/$0.60 per 1M in/out, cache read $0.015; 1M context; multimodal; thinking cannot be disabled (effort low..max); weights promised Oct 23; benchmarks Automation-Bench 62%, ALE 30%, DeepSWE 74%, BabyVision 91%. Day-0 channels: free on OpenRouter 72h, free on OpenCode 3 days, free in Cline, Ollama (US-hosted, zero retention), Vercel AI Gateway free until Oct 22, AntSeed; MiniMax Code unlimited M3.1 Flash to Oct 25, M Plan 50% off first month to Oct 31. A "preview" version (M3.1-Flash-Preview) existed on MiniMax Code since Sept 27. Treat Space Bunny, M3.1 Flash Preview and M3.1 Flash as the same product line.
For EACH tweet return a JSON object:
- id: string (copy)
- relevant: true only if substantively about this model (behavior, output, price, speed, identity reveal, availability, comparison including it, partner announcement). Generic multi-item AI news digests that mention it as one bullet are relevant=true but kind=news_digest. Unrelated "M3.1"/"bunny"/MiniMax video (Hailuo/H3) posts are relevant=false.
- kind: one of goodcase | badcase | eval_positive | eval_negative | eval_mixed | comparison | pricing_plan | speed | identity_reveal | official | partner_channel | news_digest | promo_spam | question | hype_repost | meme | other
  goodcase = author describes a concrete task they ran with the model AND the outcome was good. badcase = concrete task with a bad outcome (bug, loop, wrong answer, failure, refusal, outage, rate limit). eval_* = verdict without concrete artifact. comparison = puts it against named models. pricing_plan = about price/plans/free offers. speed = about tok/s or latency. identity_reveal = reacts to Space Bunny == MiniMax reveal. official = MiniMax accounts. partner_channel = a provider/tool (OpenRouter, Cline, OpenCode, Ollama, Vercel, Together, Kilo, Roo, AntSeed...) announcing availability/integration. news_digest = newsletter/aggregator/AI-generated digest. hype_repost = just relays the announcement with excitement, no own usage. promo_spam = affiliate/engagement bait/crypto. meme = joke/image-only reaction.
- first_hand: true if author claims to have personally used the model (any version).
- task: one of frontend_web | game | graphics_3d | agentic_workflow | debugging | refactor_migration | backend_data | long_context | multimodal_vision | writing_nontech | tool_calling | reasoning_math | research_analysis | speed_latency | cost | general | none
- sentiment: integer -2..2 toward the model/launch (0 = neutral/no verdict).
- vs: list of other models explicitly compared (normalize: "Sonnet 5.5", "Opus 5.5", "Haiku 5.5", "GPT-6", "GPT-5.6", "Gemini 3.8 Flash", "GLM-5.3-Flash", "DeepSeek V4.1 Flash", "MiMo-V2.6-Flash", "Kimi K3", "Qwen", "Grok", "M3", "Hy4", "Step 5", "Nemotron 3" ...), else [].
- channels: list of tools/providers the author says they used or that the tweet announces (normalize: "OpenRouter","OpenCode","Cline","Ollama","Vercel AI Gateway","MiniMax Code","MiniMax API","Claude Code","Kilo","Roo","Cursor","Together","AntSeed","Zed","Droid","Hermes","Codex CLI","Copilot","LM Studio","Pi"...), else [].
- topics: list from [price, speed, weights_opensource, identity_reveal, benchmarks, availability_bugs, rate_limit, trust_china, context_window, multimodal, thinking_effort, free_offer, comparison, agentic, hallucination, tool_calling] that apply (can be empty).
- claims: up to 3 short concrete claims in English (numbers, durations, artifacts, failure modes). [] if none.
- summary_zh: one Chinese sentence (<=40 chars).
Output ONLY a JSON array, same order as input, no prose."""

def load():
    pool={}
    for f in sorted(glob.glob(str(E/'merged-*.json'))):
        if f.endswith('merged-ds.json'): continue
        for r in json.loads(Path(f).read_text()):
            old=pool.get(r['id'])
            if old: old['matched']=sorted(set(old['matched'])|set(r['matched']))
            else: pool[r['id']]=r
    return pool

def batch_call(items):
    payload=[dict(id=i['id'], author=i['author'], followers=i.get('followers'), bio=(i.get('bio') or '')[:80], lang=i.get('lang'), created=(i.get('created') or '')[:16], likes=i.get('likes'), views=i.get('views'), in_reply=bool(i.get('in_reply_to')), media=i.get('media'), quoted=(i.get('quoted_text') or '')[:150], text=i['text'][:1500]) for i in items]
    for attempt in range(3):
        try:
            m=client.messages.create(model=MODEL, max_tokens=9000, system=SYSTEM, messages=[{"role":"user","content":json.dumps(payload, ensure_ascii=False)}])
            txt=''.join(b.text for b in m.content if getattr(b,'type',None)=='text')
            s=txt.find('['); e=txt.rfind(']')
            arr=json.loads(txt[s:e+1])
            if len(arr)!=len(items): raise ValueError(f'len {len(arr)}!={len(items)}')
            for a,i in zip(arr,items): a['id']=i['id']
            return arr
        except Exception as ex:
            print('  retry', attempt, type(ex).__name__, str(ex)[:160], flush=True); time.sleep(2+attempt*3)
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
    results=dict(done); lock=__import__('threading').Lock(); n=[0]
    def work(b):
        arr=batch_call(b)
        with lock:
            for a in arr: results[a['id']]=a
            n[0]+=1
            if n[0]%5==0 or n[0]==len(batches):
                OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1)); print('batch',n[0],'/',len(batches), flush=True)
    with cf.ThreadPoolExecutor(6) as ex: list(ex.map(work,batches))
    OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1))
    kinds={}
    for r in results.values(): kinds[r.get('kind')]=kinds.get(r.get('kind'),0)+1
    print('DONE', len(results), kinds, flush=True)
if __name__=='__main__': main()
