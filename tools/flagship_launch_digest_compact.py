"""Digest flagship launch-window evidence into per-model sections for reading."""
import json,re,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'reports/2026-10-02-flagship-launch'; E=D/'evidence'
rows={}
for f in ['merged.json','merged-part.json']:
    p=E/f
    if p.exists():
        for r in json.loads(p.read_text()):
            o=rows.setdefault(r['id'],r); o['matched']=sorted(set(o.get('matched',[]))|set(r.get('matched',[])))
rows=list(rows.values()); print('pool',len(rows))
OFFICIAL={'Kimi_Moonshot','Kimi_Moonshot_AI','Zai_org','deepseek_ai','XiaomiMiMo','Alibaba_Qwen','AnthropicAI','claudeai','MiniMax_AI','MiniMaxAgent'}
PARTNERS={'vllm_project','sglproject','lmsysorg','huggingface','ClementDelangue','UnslothAI','ollama','LMStudioAI','NVIDIAAIDev','AMD','OpenRouterAI','OpenRouter','togethercompute','FireworksAI_HQ','basetenco','novita_labs','modal_labs','nebiusai','vercel','GroqInc','CerebrasSystems','ArtificialAnlys','lmarena_ai','arena','opencode','cline','cursor_ai','kilocode','Perplexity_ai','databricks','DigitalOcean'}
def tagset(r): return {m.split(':')[0] for m in r['matched']}
def fam(tag): return re.sub(r'_(off|part\d?|top|oss)$','',tag)
fams=collections.OrderedDict()
for r in rows:
    for t in tagset(r):
        if t.startswith('probe'): fams.setdefault(t,[]).append(r); continue
        fams.setdefault(fam(t),[]).append(r)
out=[]
def line(r,launch=None):
    d=(r['created'] or '')[:10]
    rel=''
    if launch and d:
        from datetime import date
        try: rel=f"D{(date.fromisoformat(d)-date.fromisoformat(launch)).days:+d} "
        except: pass
    return f"- {rel}{(r['created'] or '')[:16]} @{r['author']} ({r.get('followers') or 0:,}) {r.get('likes') or 0}赞/{(r.get('views') or 0):,}展示 | {r['text'][:260].replace(chr(10),' ')} | {r['url']}"
LAUNCH={'k3':'2026-07-16','glm53':'2026-08-14','glm52':'2026-06-13','dsv4pro':'2026-08-13','dsv4':'2026-04-22','mimopro':'2026-09-21','qwen':None,'sonnet55':None,'m3':'2026-06-01'}
for f,rs in fams.items():
    rs={r['id']:r for r in rs}.values(); rs=sorted(rs,key=lambda r:r['created'] or '')
    L=LAUNCH.get(f)
    off=[r for r in rs if r['author'] in OFFICIAL]; part=[r for r in rs if r['author'] in PARTNERS]
    comm=[r for r in rs if r['author'] not in OFFICIAL|PARTNERS]
    out.append(f"\n\n# {f}  (n={len(rs)}, official {len(off)}, partners {len(part)}, community {len(comm)})")
    out.append("## official (chronological)"); out+= [line(r,L) for r in off]
    out.append("## partners (chronological)"); out+= [line(r,L) for r in part[:40]]
    top=sorted(comm,key=lambda r:-(r.get('likes') or 0))[:22]
    out.append("## community top by likes"); out+= [line(r,L) for r in top]
    oss=[r for r in comm if any(t.endswith('_oss') for t in tagset(r))]
    oss=sorted(oss,key=lambda r:-(r.get('likes') or 0))[:12]
    out.append("## community open-source / inference angle"); out+= [line(r,L) for r in oss]
(D/'digest-compact.md').write_text('\n'.join(out)); print('written', len(out),'lines')
