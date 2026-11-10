"""Bounded, resumable GTM research using the repo's read-only X client.
Outputs query manifest + timestamped normalized tweets, preserving raw API data.
Usage: .venv/bin/python tools/model_gtm_scan_20260921.py
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.xclient import XDataClient
OUT=ROOT/'reports/2026-09-21-model-gtm/evidence'
OUT.mkdir(parents=True,exist_ok=True)
q=[]
def add(tag,query,mode='Top',pages=2): q.append(dict(tag=tag,query=query+' -filter:retweets',mode=mode,max_pages=pages))
add('glm_official','from:Zai_org since:2026-08-10 until:2026-09-23','Latest',3)
add('deepseek_official','from:deepseek_ai since:2026-08-01 until:2026-09-23','Latest',3)
add('mimo_latest','(mimo OR xiaomimimo) since:2026-09-15 until:2026-09-23','Latest',3)
add('mimo26','("MiMo-V2.6" OR "mimo v2.6" OR "mimo 2.6" OR "Live RL") since:2026-09-14 until:2026-09-23','Top',3)
for vendor,kw,since in [('glm','("GLM-5.3" OR "GLM-5.3-Flash" OR "ox-alpha")','2026-08-14'),('deepseek','("DeepSeek-V4.1" OR "DeepSeek V4.1" OR "deepseek 4.1")','2026-09-01'),('mimo','(mimo OR xiaomimimo)','2026-03-10')]:
    for tag,terms in [('launch','(launch OR release OR introducing OR available OR open-source)'),('channels','(openrouter OR opencode OR cline OR kilo OR hermes OR ollama OR fireworks OR together OR baseten)'),('commercial','(price OR pricing OR free OR discount OR subscription OR credits OR orbit)'),('usecases','(workflow OR production OR customer OR business OR coding OR agent OR desktop)'),('friction','(slow OR failed OR expensive OR broken OR limit OR latency OR refund)')]:
        add(vendor+'_'+tag,f'{kw} {terms} since:{since} until:2026-09-23')
add('mimo_march','(mimo OR "hunter alpha") since:2026-03-10 until:2026-03-26','Top',3)
add('mimo_april','(mimo) (orbit OR "100T" OR "2.5" OR free) since:2026-04-20 until:2026-05-01','Top',3)
add('mimo_sept','(mimo) (ultraspeed OR desktop OR "live rl" OR "2.6") since:2026-09-01 until:2026-09-23','Top',3)
add('glm_ox','("ox alpha" OR "ox-alpha") since:2026-08-19 until:2026-08-27','Top',3)
add('deepseek_launchweek','deepseek since:2026-09-09 until:2026-09-15','Top',3)
add('minimax_context','("M3.1" OR "M3.1-Flash" OR "M3.1 Flash") (minimax OR 海螺) since:2026-08-01 until:2026-09-23','Top',2)
if '--supplement' in sys.argv:
    q=[]
    add('mimo_official_sept','from:XiaomiMiMo since:2026-09-01 until:2026-09-23','Latest',4)
    add('mimo_official_spring','from:XiaomiMiMo since:2026-03-10 until:2026-05-30','Top',3)
    add('deepseek_partner_official','(from:opencode OR from:cline OR from:OpenRouter OR from:OpenRouterAI OR from:ollama) (deepseek OR "V4.1") since:2026-09-09 until:2026-09-16','Top',3)
    add('glm_partner_official','(from:opencode OR from:OpenRouter OR from:OpenRouterAI OR from:cline) ("GLM" OR "Ox Alpha" OR "ox-alpha") since:2026-08-19 until:2026-08-30','Top',3)
    for vendor,kw,since in [('glm','("GLM-5.3" OR "GLM 5.3" OR "ox-alpha")','2026-08-20'),('deepseek','("DeepSeek-V4.1" OR "DeepSeek V4.1" OR "DeepSeek 4.1")','2026-09-09'),('mimo','(mimo OR xiaomimimo)','2026-09-15')]:
        add(vendor+'_oss_top',f'{kw} (gguf OR mlx OR vllm OR sglang OR quantization OR exl3 OR license OR weights OR local OR GPU) since:{since} until:2026-09-23','Top',3)
        add(vendor+'_negative_latest',f'{kw} (slow OR timeout OR broken OR fails OR failure OR unusable OR disappointed OR worse OR hallucination OR 慢 OR 失败 OR 不行 OR 限额) since:{since} until:2026-09-23','Latest',3)
        add(vendor+'_oss_maintainers',f'{kw} (from:UnslothAI OR from:MiaAI_lab OR from:sglproject OR from:vllm_project OR from:ivanfioravanti OR from:Thom_Wolf OR from:reach_vb OR from:lmstudio) since:{since} until:2026-09-23','Latest',2)
if '--focused' in sys.argv:
    q=[]
    add('mimo_negative_scoped','("MiMo-V2.6" OR "MiMo V2.6" OR "MiMo 2.6" OR "mimo-v2.5" OR "mimo 2.5" OR "Xiaomi MiMo") (slow OR timeout OR broken OR fails OR failure OR unusable OR disappointed OR worse OR hallucination OR 慢 OR 失败 OR 不行 OR 限额) since:2026-09-01 until:2026-09-23','Latest',3)
    add('mimo_hunter_scoped','("Hunter Alpha" OR "MiMo-V2-Pro" OR "Xiaomi MiMo") since:2026-03-10 until:2026-03-27','Top',2)
key=None
for line in (ROOT/'.env').read_text().splitlines():
    if line.startswith('TWITTERAPI_KEY='): key=line.split('=',1)[1].strip().strip('"').strip("'")
if not key: raise SystemExit('TWITTERAPI_KEY missing')
client=XDataClient(api_key=key)
manifest_path=OUT/'queries.json'
manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else []
done={x['tag'] for x in manifest if x.get('status')=='ok'}
for item in q:
    if item['tag'] in done: continue
    stamp=datetime.now(timezone.utc).isoformat()
    rows=[]
    try:
        for t in client.search_recent(item['query'],query_type=item['mode'],max_pages=item['max_pages']):
            rows.append(dict(id=t.id,url=t.url,text=t.text,created=t.created_at.isoformat() if t.created_at else None,author=t.author.handle,author_name=t.author.name,followers=t.author.followers,likes=t.like_count,retweets=t.retweet_count,replies=t.reply_count,quotes=t.quote_count,views=t.view_count,lang=t.lang,raw=t.raw,collected_at=stamp))
        item.update(status='ok',count=len(rows),collected_at=stamp)
    except Exception as e: item.update(status='error',error=type(e).__name__,count=len(rows),collected_at=stamp)
    (OUT/(item['tag']+'.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=1))
    manifest.append(item);manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=1))
    print(item['tag'],item['status'],len(rows),flush=True)
print('COMPLETE',flush=True)
