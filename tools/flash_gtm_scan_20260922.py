"""Round 2: Flash-tier GTM deep scan (GLM-5.3-Flash / DeepSeek-V4.1-Flash / MiMo-V2.6-Flash)
Deeper angles than round 1: head-to-head, retention windows, unit economics,
zh-language reception, deployment/quant, channel rankings, MiniMax baseline.
Usage: .venv/bin/python tools/flash_gtm_scan_20260922.py [--wave2]
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient

OUT = ROOT / 'reports/2026-09-22-flash-gtm/evidence'
OUT.mkdir(parents=True, exist_ok=True)
UNTIL = '2026-09-23'
q = []
def add(tag, query, mode='Top', pages=3):
    q.append(dict(tag=tag, query=query + ' -filter:retweets', mode=mode, max_pages=pages))

GLM = '("GLM-5.3-Flash" OR "GLM 5.3 Flash" OR "glm-5.3-flash")'
DS  = '("DeepSeek-V4.1-Flash" OR "V4.1-Flash" OR "deepseek-flash" OR "DeepSeek V4.1 Flash")'
MM  = '("MiMo-V2.6-Flash" OR "MiMo V2.6 Flash" OR "mimo-flash" OR "MiMo 2.6 Flash")'

# --- A. official vendor + Flash-tier owners ---------------------------------
add('off_zai',      f'from:Zai_org since:2026-08-14 until:{UNTIL}', 'Latest', 4)
add('off_deepseek', f'from:deepseek_ai since:2026-08-25 until:{UNTIL}', 'Latest', 4)
add('off_mimo',     f'from:XiaomiMiMo since:2026-09-10 until:{UNTIL}', 'Latest', 4)
add('off_minimax',  f'(from:MiniMax__AI OR from:MiniMax_AI OR from:Hailuo_AI) since:2026-08-01 until:{UNTIL}', 'Latest', 4)

# --- B. channel / partner surface per Flash ---------------------------------
PARTNERS = '(from:opencode OR from:cline OR from:OpenRouterAI OR from:OpenRouter OR from:kilocode OR from:ollama OR from:vllm_project OR from:sglproject OR from:LMStudioAI OR from:UnslothAI OR from:FireworksAI_HQ OR from:basetenco OR from:togethercompute OR from:novita_labs)'
add('ch_glm',  f'{PARTNERS} (GLM OR "ox alpha" OR "ox-alpha") since:2026-08-18 until:2026-09-10', 'Latest', 4)
add('ch_ds',   f'{PARTNERS} (deepseek OR "V4.1") since:2026-09-08 until:{UNTIL}', 'Latest', 4)
add('ch_mimo', f'{PARTNERS} (mimo OR xiaomi) since:2026-09-18 until:{UNTIL}', 'Latest', 4)
add('ch_rank', f'(from:OpenRouterAI OR from:OpenRouter OR from:opencode) (ranking OR rankings OR leaderboard OR "top model" OR "most used" OR "tokens" OR weekly) since:2026-08-18 until:{UNTIL}', 'Latest', 4)

# --- C. Flash vs Flash head-to-head -----------------------------------------
add('h2h_pair',  f'({GLM} OR {DS} OR {MM}) (vs OR versus OR compared OR comparison OR "head to head" OR benchmark OR tested) since:2026-08-20 until:{UNTIL}', 'Top', 4)
add('h2h_tier',  f'("flash model" OR "flash models" OR "flash tier" OR "cheap model" OR "small model") (agent OR coding OR router OR default OR cost) since:2026-08-20 until:{UNTIL}', 'Top', 3)

# --- D. retention windows: are people still using it weeks later? -----------
add('ret_glm',  f'{GLM} since:2026-09-05 until:{UNTIL}', 'Latest', 4)
add('ret_ds',   f'{DS} since:2026-09-15 until:{UNTIL}', 'Latest', 4)
add('ret_mimo', f'{MM} since:2026-09-21 until:{UNTIL}', 'Latest', 4)
add('ret_habit', f'("daily driver" OR "default model" OR "switched to" OR "switched from" OR "replaced" OR "cancelled my" OR "canceled my" OR "stopped using") (GLM OR DeepSeek OR MiMo OR flash) since:2026-08-20 until:{UNTIL}', 'Top', 4)

# --- E. unit economics ------------------------------------------------------
add('econ_cost', f'({GLM} OR {DS} OR {MM}) (cost OR bill OR spend OR "per million" OR cache OR cached OR cheap OR pricing OR credits) since:2026-08-20 until:{UNTIL}', 'Top', 4)
add('econ_cache', f'(deepseek OR GLM OR mimo) (cache OR caching OR "cache hit" OR "cached input") (price OR cost OR token OR tokens) since:2026-09-01 until:{UNTIL}', 'Top', 3)

# --- F. Chinese-language reception ------------------------------------------
add('zh_flash', f'(GLM OR DeepSeek OR MiMo OR 智谱 OR 小米) (Flash OR 闪电 OR 便宜 OR 性价比 OR 编程 OR 代码 OR 智能体) lang:zh since:2026-08-20 until:{UNTIL}', 'Top', 4)
add('zh_pair',  f'(GLM OR DeepSeek OR MiMo) (对比 OR 实测 OR 体验 OR 日常 OR 默认 OR 换成 OR 主力) lang:zh since:2026-08-20 until:{UNTIL}', 'Top', 4)

# --- G. deployment / quantization / inference -------------------------------
add('oss_quant', f'({GLM} OR {DS} OR {MM}) (gguf OR mlx OR awq OR fp8 OR int4 OR quant OR quantization OR vllm OR sglang OR "llama.cpp" OR lmstudio OR "tok/s" OR tokens/s) since:2026-08-20 until:{UNTIL}', 'Top', 4)
add('oss_local', f'({GLM} OR {DS} OR {MM}) (local OR locally OR "running it" OR 3090 OR 4090 OR 5090 OR M3 OR M4 OR spark OR "RTX" OR VRAM) since:2026-08-20 until:{UNTIL}', 'Top', 4)

# --- H. friction / negative -------------------------------------------------
add('neg_glm',  f'{GLM} (slow OR latency OR timeout OR broken OR fails OR failed OR loop OR looping OR stuck OR worse OR bad OR hallucin OR 慢 OR 失败 OR 不行) since:2026-08-20 until:{UNTIL}', 'Latest', 4)
add('neg_ds',   f'{DS} (slow OR latency OR timeout OR broken OR fails OR failed OR loop OR stuck OR worse OR bad OR hallucin OR 慢 OR 失败 OR 不行) since:2026-09-09 until:{UNTIL}', 'Latest', 4)
add('neg_mimo', f'({MM} OR "MiMo-V2.6") (slow OR latency OR timeout OR broken OR fails OR failed OR loop OR stuck OR worse OR bad OR hallucin OR 慢 OR 失败) since:2026-09-19 until:{UNTIL}', 'Latest', 4)

# --- I. MiniMax baseline ----------------------------------------------------
add('mx_m31', f'("M3.1" OR "M3.1-Flash" OR "MiniMax M3" OR "MiniMax-M3" OR "MiniMax M2" OR "MiniMax-M2") since:2026-08-01 until:{UNTIL}', 'Top', 4)
add('mx_dev', f'(minimax OR 海螺 OR MiniMax) (coding OR agent OR API OR openrouter OR opencode OR cline OR 编程 OR 智能体) since:2026-08-20 until:{UNTIL}', 'Top', 4)

# --- J. adjacent flash-tier competitors (tier framing) ----------------------
add('adj_tier', f'(qwen OR kimi OR "gpt-5" OR gemini OR grok) (flash OR mini OR turbo OR lite OR "fast model") (cheap OR agent OR coding OR router OR price) since:2026-09-01 until:{UNTIL}', 'Top', 3)

if '--wave2' in sys.argv:
    q = []
    add('w2_mimo_day1', f'(mimo OR xiaomimimo OR "MiMo-V2.6") since:2026-09-21 until:{UNTIL}', 'Latest', 5)
    add('w2_mimo_top',  f'(mimo OR "MiMo-V2.6" OR "Live RL") since:2026-09-20 until:{UNTIL}', 'Top', 4)
    add('w2_glm_sept',  f'(GLM OR "z.ai" OR zai) (flash OR coding OR plan OR agent) since:2026-09-08 until:{UNTIL}', 'Top', 4)
    add('w2_ds_week2',  f'(deepseek OR "V4.1") (flash OR agent OR coding OR api OR cost) since:2026-09-14 until:{UNTIL}', 'Top', 4)
    add('w2_workflow',  f'(opencode OR cline OR "claude code" OR roo OR kilo OR crush OR droid) (GLM OR deepseek OR mimo) (flash OR cheap OR free OR default) since:2026-08-20 until:{UNTIL}', 'Top', 4)
    add('w2_buyers',    f'(startup OR SaaS OR "we switched" OR "our agents" OR "in production" OR "inference bill") (GLM OR deepseek OR mimo OR flash) since:2026-08-20 until:{UNTIL}', 'Top', 4)

key = None
for line in (ROOT / '.env').read_text().splitlines():
    if line.startswith('TWITTERAPI_KEY='):
        key = line.split('=', 1)[1].strip().strip('"').strip("'")
if not key:
    raise SystemExit('TWITTERAPI_KEY missing')
client = XDataClient(api_key=key)
manifest_path = OUT / 'queries.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
done = {x['tag'] for x in manifest if x.get('status') == 'ok'}
for item in q:
    if item['tag'] in done:
        continue
    stamp = datetime.now(timezone.utc).isoformat()
    rows = []
    try:
        for t in client.search_recent(item['query'], query_type=item['mode'], max_pages=item['max_pages']):
            rows.append(dict(id=t.id, url=t.url, text=t.text,
                             created=t.created_at.isoformat() if t.created_at else None,
                             author=t.author.handle, author_name=t.author.name,
                             followers=t.author.followers, likes=t.like_count,
                             retweets=t.retweet_count, replies=t.reply_count,
                             quotes=t.quote_count, views=t.view_count, lang=t.lang,
                             raw=t.raw, collected_at=stamp))
        item.update(status='ok', count=len(rows), collected_at=stamp)
    except Exception as e:
        item.update(status='error', error=type(e).__name__, count=len(rows), collected_at=stamp)
    (OUT / (item['tag'] + '.json')).write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    manifest.append(item)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(item['tag'], item['status'], len(rows), flush=True)
print('COMPLETE', flush=True)
