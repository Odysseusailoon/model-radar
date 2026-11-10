"""Flagship launch-window scan: what did each vendor + its partners do in the launch week.
Run: TWITTERAPI_MIN_INTERVAL=1.2 .venv/bin/python tools/flagship_launch_scan_20261002.py
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from app.xclient import XDataClient
OUT=ROOT/'reports/2026-10-02-flagship-launch/evidence'; OUT.mkdir(parents=True,exist_ok=True)
PART='(from:vllm_project OR from:sglproject OR from:lmsysorg OR from:huggingface OR from:ClementDelangue OR from:OpenRouterAI OR from:OpenRouter OR from:togethercompute OR from:FireworksAI_HQ OR from:basetenco OR from:novita_labs OR from:UnslothAI OR from:ollama OR from:LMStudioAI OR from:ArtificialAnlys OR from:lmarena_ai OR from:arena OR from:opencode OR from:cline OR from:cursor_ai OR from:NVIDIAAIDev OR from:AMD OR from:vercel OR from:GroqInc OR from:CerebrasSystems OR from:modal_labs OR from:nebiusai OR from:kilocode)'
NR='-filter:retweets'
Q=[]
def add(tag,query,mode='Latest',pages=3): Q.append(dict(tag=tag,query=query,mode=mode,max_pages=pages))
F={
 'k3':      dict(off='(from:Kimi_Moonshot OR from:Kimi_Moonshot_AI)', kw='(Kimi K3 OR "K3" OR kimi-k3)', since='2026-07-14', until='2026-08-01'),
 'glm53':   dict(off='from:Zai_org', kw='(GLM-5.3 OR "GLM 5.3" OR glm-5.3)', since='2026-08-12', until='2026-09-01'),
 'glm52':   dict(off='from:Zai_org', kw='(GLM-5.2 OR "GLM 5.2" OR glm-5.2)', since='2026-06-11', until='2026-06-24'),
 'dsv4pro': dict(off='from:deepseek_ai', kw='(DeepSeek V4 OR DeepSeek-V4 OR "V4 Pro" OR "V4-Pro" OR deepseek-v4)', since='2026-08-10', until='2026-08-22'),
 'dsv4':    dict(off='from:deepseek_ai', kw='(DeepSeek V4 OR DeepSeek-V4 OR deepseek-v4)', since='2026-04-15', until='2026-05-02'),
 'mimopro': dict(off='from:XiaomiMiMo', kw='(MiMo-V2.6 OR "MiMo V2.6" OR mimo-v2.6 OR "MiMo Pro")', since='2026-09-19', until='2026-09-27'),
 'qwen':    dict(off='from:Alibaba_Qwen', kw='(Qwen3.8 OR "Qwen 3.8" OR Qwen3.7 OR "Qwen 3.7" OR Qwen3.6 OR "Qwen 3.6" OR "Qwen4" OR "Qwen 4")', since='2026-06-01', until='2026-10-02'),
 'sonnet55':dict(off='(from:AnthropicAI OR from:claudeai)', kw='("Sonnet 5.5" OR "Opus 5.5" OR "Claude 5.5")', since='2026-09-20', until='2026-10-02'),
 'm3':      dict(off='(from:MiniMax_AI OR from:MiniMaxAgent)', kw='(MiniMax-M3 OR "MiniMax M3" OR minimax-m3)', since='2026-05-29', until='2026-06-12'),
}
for k,f in F.items():
    w=f"since:{f['since']} until:{f['until']}"
    add(f'{k}_off',  f"{f['off']} {w} {NR}", 'Latest', 5)
    add(f'{k}_part', f"{PART} {f['kw']} {w} {NR}", 'Latest', 4)
    add(f'{k}_top',  f"{f['kw']} {w} {NR}", 'Top', 4)
    add(f'{k}_oss',  f"{f['kw']} (weights OR \"open source\" OR \"open-source\" OR huggingface OR gguf OR vllm OR sglang OR quant OR mlx OR \"tech report\" OR license OR MIT OR Apache) {w} {NR}", 'Top', 3)
# probes for dates
add('probe_ds_official_2026', 'from:deepseek_ai since:2026-03-01 until:2026-10-02 -filter:retweets', 'Latest', 6)
add('probe_qwen_official_2026', 'from:Alibaba_Qwen since:2026-03-01 until:2026-10-02 -filter:retweets', 'Latest', 6)
add('probe_kimi_official_2026', '(from:Kimi_Moonshot OR from:Kimi_Moonshot_AI) since:2026-06-01 until:2026-10-02 -filter:retweets', 'Latest', 5)
add('probe_anthropic_2026', '(from:AnthropicAI OR from:claudeai) since:2026-07-01 until:2026-10-02 -filter:retweets', 'Latest', 5)
def key():
    for l in (ROOT/'.env').read_text().splitlines():
        if l.startswith('TWITTERAPI_KEY='): return l.split('=',1)[1].strip()
c=XDataClient(api_key=key()); mp=OUT/'queries.json'; manifest=json.loads(mp.read_text()) if mp.exists() else []
done={(m['tag'],m['mode']) for m in manifest if m.get('status')=='ok'}
merged_p=OUT/'merged.json'; seen={r['id']:r for r in json.loads(merged_p.read_text())} if merged_p.exists() else {}
for q in Q:
    if (q['tag'],q['mode']) in done: continue
    stamp=datetime.now(timezone.utc).isoformat(); n=0; status='ok'; err=None
    try:
        for t in c.search_recent(q['query'],query_type=q['mode'],max_pages=q['max_pages']):
            r=seen.setdefault(t.id,dict(id=t.id,url=t.url or f'https://x.com/i/status/{t.id}',text=t.text,created=t.created_at.isoformat() if t.created_at else None,lang=t.lang,author=t.author.handle,author_name=t.author.name,followers=t.author.followers,likes=t.like_count,retweets=t.retweet_count,replies=t.reply_count,views=t.view_count,urls=[u.get('expanded_url') for u in (t.raw.get('entities',{}) or {}).get('urls',[]) if u.get('expanded_url')],matched=[]))
            k=f"{q['tag']}:{q['mode'][0]}"
            if k not in r['matched']: r['matched'].append(k)
            n+=1
    except Exception as e: status='error'; err=f'{type(e).__name__}: {e}'[:200]
    manifest.append(dict(tag=q['tag'],mode=q['mode'],query=q['query'],status=status,error=err,count=n,collected_at=stamp))
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=1)); merged_p.write_text(json.dumps(list(seen.values()),ensure_ascii=False,indent=1))
    print(q['tag'],status,n,'total',len(seen),flush=True)
print('COMPLETE',len(seen),flush=True)
