"""Batch-tag M3.1 Flash D+1..D+10 tweets with Claude Haiku (12/batch, 6 threads, resumable).
Reads reports/2026-10-29-m31-flash-d10/evidence/merged-{main,windows}.json, writes classified.json.
Baseline (merged-baseline.json, DeepSeek) is NOT classified — it is only used for volume.
Run: .venv/bin/python tools/m31_flash_d10_classify_20261029.py
"""
from __future__ import annotations
import json, os, sys, time, glob, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'reports/2026-10-29-m31-flash-d10/evidence'
OUT = E / 'classified.json'
import anthropic


def env(k):
    for line in (ROOT / '.env').read_text().splitlines():
        if line.startswith(k + '='):
            return line.split('=', 1)[1].strip().strip('"').strip("'")


client = anthropic.Anthropic(
    api_key=os.environ.get('ANTHROPIC_API_KEY') or env('ANTHROPIC_API_KEY'),
    base_url=os.environ.get('ANTHROPIC_BASE_URL') or env('ANTHROPIC_BASE_URL'),
    timeout=120, max_retries=3)
MODEL = os.environ.get('ANTHROPIC_DEFAULT_HAIKU_MODEL') or 'claude-haiku-4-5'

SYSTEM = """You tag tweets about MiniMax's model "M3.1 Flash" (MiniMax-M3.1-Flash) collected for the window 2026-10-20 .. 2026-10-29, i.e. days 1-10 AFTER its 2026-10-19 public launch. This is a RETENTION study, not a launch study: the interesting question is who is still using it a week later, and what the launch-day complaints turned into.

Background. Launch 2026-10-19 11:56 UTC. The stealth model "Space Bunny (Alpha)" (free on OpenRouter/OpenCode from 2026-09-23, #1 by tokens there) was an earlier build of M3.1 Flash; treat Space Bunny, M3.1-Flash-Preview and M3.1 Flash as one product line. Official claims: 1/3 the cost and 3x the speed of M3; API $0.15/$0.60 per 1M in/out, cache read $0.015; 1M context; multimodal; thinking cannot be disabled (effort low..max); benchmarks Automation-Bench 62%, ALE 30%, DeepSWE 74%, BabyVision 91%.
Window timeline: free offers expired (OpenRouter 72h free ended ~10/22, OpenCode 3 days, Vercel AI Gateway free until 10/22, MiniMax Code unlimited to 10/25, M Plan 50%-off to 10/31); open weights were promised for 10/23; a Fireworks x MiniMax Flash workshop happened 10/28.
Launch-day concentrated complaints, which you should detect recurrences or fixes of: (1) Japanese/Chinese language mixing in output, (2) benchmaxxing / contamination accusations, (3) prompt-cache priced 5x higher than rivals, (4) thinking not disableable, defaults to max effort.

For EACH tweet return a JSON object:
- id: string (copy)
- relevant: true only if substantively about this model (behavior, output, price, speed, availability, weights/local deploy, provider hosting, comparison including it, retention/churn). Multi-item AI news digests that mention it as one bullet are relevant=true with kind=news_digest. Unrelated "M3.1"/"bunny"/MiniMax video (Hailuo/H3) posts are relevant=false.
- kind: one of goodcase | badcase | eval_positive | eval_negative | eval_mixed | comparison | pricing_plan | speed | official | partner_channel | weights_release | local_deploy | provider_host | workshop_content | retention_keep | retention_churn | news_digest | promo_spam | question | hype_repost | meme | other
  goodcase = author describes a concrete task they ran AND the outcome was good. badcase = concrete task with a bad outcome (bug, loop, wrong answer, failure, refusal, outage, rate limit). eval_* = verdict without a concrete artifact. weights_release = about the open-weights drop itself (HF repo, license, size, availability). local_deploy = author runs it locally or self-hosted (llama.cpp/GGUF/MLX/vLLM/SGLang/quants/own GPUs). provider_host = a third-party inference provider (Fireworks, Together, Baseten, Novita, DeepInfra, Groq, Cerebras, SiliconFlow...) serving it. workshop_content = the Fireworks/MiniMax workshop, webinar, cookbook, tutorial, fine-tuning guide. retention_keep = author says they are STILL using it after the first days / made it a daily driver / started paying. retention_churn = author says they stopped, switched away, went back to another model, cancelled, or let the sub lapse. Prefer retention_keep/retention_churn over eval_* when the tweet's point is continued or discontinued use.
- first_hand: true if the author claims to have personally used the model (any version).
- retention: one of still_using | switched_away | trial_only | considering | unclear — the author's own usage state as of this tweet. Use unclear when the tweet says nothing about it.
- days_used: integer number of days of use the author claims, or null.
- task: one of frontend_web | game | graphics_3d | agentic_workflow | debugging | refactor_migration | backend_data | long_context | multimodal_vision | writing_nontech | tool_calling | reasoning_math | research_analysis | speed_latency | cost | deployment | none
- sentiment: integer -2..2 toward the model (0 = neutral/no verdict).
- vs: list of other models explicitly compared (normalize: "Sonnet 5.5", "Opus 5.5", "Haiku 5.5", "GPT-6", "GPT-5.6", "Gemini 3.8 Flash", "GLM-5.3-Flash", "DeepSeek V4.1 Flash", "MiMo-V2.6-Flash", "Kimi K3", "Qwen", "Grok", "M3", "M3.1 Pro", "Hy4", "Step 5", "Nemotron 3" ...), else [].
- channels: list of tools/providers the author says they used or that the tweet announces (normalize: "OpenRouter","OpenCode","Cline","Ollama","Vercel AI Gateway","MiniMax Code","MiniMax API","Claude Code","Kilo","Roo","Cursor","Together","Fireworks","Baseten","Novita","DeepInfra","Groq","Cerebras","SiliconFlow","AntSeed","Zed","Droid","Hermes","Codex CLI","Copilot","LM Studio","llama.cpp","vLLM","SGLang","Hugging Face","Pi"...), else [].
- topics: list from [price, cache_price, speed, weights_opensource, local_inference, quantization, finetune, benchmarks, benchmaxx_doubt, availability_bugs, rate_limit, trust_china, context_window, multimodal, thinking_effort, language_mixing, free_offer_ended, comparison, agentic, hallucination, tool_calling, openrouter_rank, workshop] that apply (can be empty).
- fix_status: one of fixed | still_broken | none — only about the four known launch-day complaints (language mixing, benchmaxx doubt, cache price, thinking not disableable). fixed = the tweet says it improved or was addressed; still_broken = the tweet reports it is still a problem; none = tweet is not about any of them.
- claims: up to 3 short concrete claims in English (numbers, durations, artifacts, failure modes). [] if none.
- summary_zh: one Chinese sentence (<=40 chars).
Output ONLY a JSON array, same order as input, no prose."""


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
    return pool


def batch_call(items):
    payload = [dict(id=i['id'], author=i['author'], followers=i.get('followers'),
                    bio=(i.get('bio') or '')[:80], lang=i.get('lang'),
                    created=(i.get('created') or '')[:16], likes=i.get('likes'), views=i.get('views'),
                    in_reply=bool(i.get('in_reply_to')), media=i.get('media'),
                    quoted=(i.get('quoted_text') or '')[:150], text=i['text'][:1500]) for i in items]
    for attempt in range(3):
        try:
            m = client.messages.create(model=MODEL, max_tokens=12000, system=SYSTEM,
                                       messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            txt = ''.join(b.text for b in m.content if getattr(b, 'type', None) == 'text')
            s = txt.find('['); e = txt.rfind(']')
            arr = json.loads(txt[s:e + 1])
            if len(arr) != len(items):
                raise ValueError(f'len {len(arr)}!={len(items)}')
            for a, i in zip(arr, items):
                a['id'] = i['id']
            return arr
        except Exception as ex:
            print('  retry', attempt, type(ex).__name__, str(ex)[:160], flush=True)
            time.sleep(2 + attempt * 3)
    return [dict(id=i['id'], relevant=None, kind='error') for i in items]


def main():
    pool = load()
    done = {}
    if OUT.exists():
        for r in json.loads(OUT.read_text()):
            if r.get('kind') != 'error':
                done[r['id']] = r
    todo = [r for r in pool.values() if r['id'] not in done]
    print('pool', len(pool), 'done', len(done), 'todo', len(todo), flush=True)
    todo.sort(key=lambda r: -(r.get('likes') or 0))
    batches = [todo[i:i + 12] for i in range(0, len(todo), 12)]
    results = dict(done); lock = __import__('threading').Lock(); n = [0]

    def work(b):
        arr = batch_call(b)
        with lock:
            for a in arr:
                results[a['id']] = a
            n[0] += 1
            if n[0] % 5 == 0 or n[0] == len(batches):
                OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1))
                print('batch', n[0], '/', len(batches), flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(work, batches))
    OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1))
    kinds = {}
    for r in results.values():
        kinds[r.get('kind')] = kinds.get(r.get('kind'), 0) + 1
    print('DONE', len(results), kinds, flush=True)


if __name__ == '__main__':
    main()
