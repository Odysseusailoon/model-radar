"""Source 20 candidates per X campaign (7 campaigns) from: 互粉名单 (T117), KOL Radar 08 pool + 01 outreach,
voidasuka-mutuals (AI bios), 10/19 outreach.json, 10/9 tpot candidates. Writes markdown + JSON; push separately."""
import json,re,math,collections
from pathlib import Path
OUT=Path('reports/2026-10-19-m31-flash-network-gtm'); 
def H(s): 
    m=re.search(r'@([A-Za-z0-9_]+)',s or ''); return (m.group(1) if m else (s or '').lstrip('@')).lower()
P={}  # handle -> record
def rec(h):
    h=h.lower()
    if h not in P: P[h]={'handle':h,'src':set(),'bio':'','themes':'','personas':'','track':'','name':'','followers':0,'rel':'','tier':'','official':'','va':'','mx_posts':0,'score08':0,'excl':''}
    return P[h]
g=json.load(open('voidasuka-graph.json')); fo={u['handle'].lower():u for u in g['followings']}; fr={u['handle'].lower():u for u in g['followers']}
for r in json.load(open('.lark-auth/hufen_rows.json')):
    if not r.get('Handle'): continue
    x=rec(r['Handle']); x['src'].add('互粉名单'); x['name']=r.get('名字') or x['name']; x['followers']=r.get('粉丝数') or x['followers']
    x['bio']=r.get('Bio') or x['bio']; x['rel']=(r.get('关系') or [''])[0]; x['tier']=(r.get('档位') or [''])[0]; x['official']=(r.get('MiniMax关系') or [''])[0]
for r in json.load(open('.lark-auth/t08_rows.json')):
    x=rec(H(r['handle'])); x['src'].add('08池'); x['name']=x['name'] or (r.get('name') or ''); x['followers']=x['followers'] or (r.get('followers') or 0)
    x['themes']=r.get('themes') or ''; x['personas']=(r.get('audience_type') or [''])[0]; x['mx_posts']=r.get('mx_posts') or 0; x['score08']=r.get('score') or 0
    x['excl']=(r.get('excluded_reason') or [''])[0] if isinstance(r.get('excluded_reason'),list) else (r.get('excluded_reason') or '')
    x['official']=x['official'] or ((r.get('relation_official') or [''])[0])
for r in json.load(open('.lark-auth/t01_recs.json')):
    x=rec(H(r['handle'])); x['src'].add('01 Outreach'); x['bio']=x['bio'] or (r.get('bio') or ''); x['name']=x['name'] or (r.get('name') or '')
    x['followers']=x['followers'] or (r.get('followers') or 0); x['personas']=x['personas'] or (r.get('personas') or [''])[0]; x['official']=x['official'] or (r.get('关系') or [''])[0]
for r in json.load(open('voidasuka-mutuals.json'))['mutuals']:
    x=rec(r['handle']); x['src'].add('互粉图谱AI'); x['bio']=x['bio'] or (r.get('bio') or ''); x['name']=x['name'] or r.get('name',''); x['followers']=x['followers'] or (r.get('followers') or 0)
for r in json.load(open(OUT/'outreach.json')):
    x=rec(r['handle']); x['src'].add('10/19 outreach'); x['track']=r.get('track',''); x['bio']=x['bio'] or r.get('profile_bio_snapshot','')
c=json.load(open('reports/2026-10-09-tpot-mutuals/candidates.json')); cl=c if isinstance(c,list) else (c.get('candidates') or list(c.values())[0])
for r in cl:
    x=rec(r['handle']); x['src'].add('10/9 tpot'); x['bio']=x['bio'] or (r.get('bio') or r.get('profile_bio') or '')
for h,x in P.items():
    u=fo.get(h) or fr.get(h) or {}
    x['va']='互粉' if (h in fo and h in fr) else ('仅我关注' if h in fo else ('仅TA关注我' if h in fr else '不在图谱'))
    x['followers']=x['followers'] or u.get('followers') or 0; x['name']=x['name'] or u.get('name','')
print('pool',len(P))

CAMP={
 1:('C1 $0.15 Frontier Challenge（成本/成功率实测）',
    [(r'benchmark|leaderboard|arena|\beval|evals\b|evaluation|artificial analysis|pricing|cost|token|price|methodolog',2),(r'swe-?bench|terminal-?bench|agent eval|aider',2)],
    {'themes':{'benchmark':2,'price_context':2,'methodology':2},'personas':{'benchmarker':3,'model_analyst':2},'track':r'评测|成本|Evals|差异测试'}, []),
 2:('C2 Can Your Agent Finish the Job（许愿式编程：编曲动画/视频剪辑/设计图转页面）',
    [(r'design engineer|designer|frontend|front-end|web dev|react|css|three\.?js|creative (director|technolog|coding|coder)|video|filmmak|music|animation|motion|generative art|ui/ux|\bux\b|product design|visual|figma|\bart\b|artist|game dev|indie game|godot|unity ?(3d|dev)',2),(r'remotion|ffmpeg|blender|suno|webgl|shader|after effects|touchdesigner|p5\.?js|vibe cod',3)],
    {'personas':{},'track':r'设计工程|多模态|实际产品|个人 Agent|自动化'}, []),
 3:('C3 MiniMax vs Real-World Engineering（同一模型 × 不同 coding agent harness）',
    [(r'opencode|cline|kilo|cursor|claude code|codex|copilot|coding agent|agentic coding|\bswe\b|software engineer|devtools|\bide\b|terminal|\bcli\b|harness|tool.?use|tool calling',2),(r'maintainer|open.?source|oss|github',1)],
    {'themes':{'agentic_coding':2,'reliability':2},'personas':{'coding_power_user':2},'track':r'Coding|编辑器|全栈|工具调用|接入|harness|Hermes'}, []),
 4:('C4 Build With MiniMax 7 天社区挑战（组织者/教程/分发）',
    [(r'community|hackathon|devrel|developer advocate|educator|tutorial|youtube|newsletter|podcast|building in public|indie hacker|founder|creator|course|teach',2),(r'host|organizer|meetup|discord',2)],
    {'themes':{'distribution':2},'personas':{'distribution':3,'KOC':1},'track':r'教程|媒体|直播|分发|中文开发者'}, []),
 5:('C5 Open Weights Countdown（推理/量化/本地部署/Infra）',
    [(r'inference|vllm|sglang|\bmlx\b|llama\.?cpp|quantiz|gguf|ollama|serving|\bgpu\b|cuda|kernel|open.?weights|huggingface|hugging face|unsloth|lmstudio|exllama|triton|throughput|latency',2),(r'infra|systems|compiler|hardware|chip',1)],
    {'themes':{'local_inference':3,'serving_speed':2},'personas':{'local_inference':3},'track':r'MLX|量化|SGLang|推理|Unsloth|自托管'}, ['vikhyatk','tenderizzation']),
 6:('C6 One Model, Many Agents（伙伴 CLI/Agent 工具的维护者、工程师、DevRel 个人号）',
    [(r'\bcli\b|coding agent|ai coding|code editor|\bide\b|agent framework|open.?source agent|autonomous coding',1),(r'\b(opencode|cline|kilo ?code|kilocode|roo ?code|goose|aider|droid|factory\.ai|crush|continue(\.dev)?|zed|openhands|openrouter|requesty|cc switch|claude code router|avante|bolt(\.new)?|lovable|replit|windsurf|trae|cursor|codex cli|gemini cli|amp|augment|sourcegraph|tabnine|codeium|pear ?ai|void editor|warp|hermes agent|hermes|openclaw|clawdbot|smolagents|langchain|langgraph|crewai|mastra|agno|letta|browser.?use|stagehand|e2b|daytona|composio)\b',3)],
    {'themes':{'agentic_coding':1,'distribution':1},'personas':{'vendor':3,'distribution':2,'coding_power_user':1},'track':r'OpenCode|CC Switch|编辑器|API 分发'}, []),
 7:('C7 The Engineering Behind M3.1-Flash（研究者/技术深度）',
    [(r'research|researcher|scientist|phd|post-?training|pre-?training|\brl\b|rlhf|reinforcement|interpretab|alignment|ml engineer|machine learning|deep learning|\bllm\b|transformer|architecture',2),(r'deepmind|openai|anthropic|meta ai|fair|nous|hugging face|allen ai|ai2|stanford|berkeley|mit|cmu|tsinghua|pku',1)],
    {'themes':{'methodology':2,'benchmark':1},'personas':{'model_analyst':2,'benchmarker':1},'track':r'研究|Evals|开源模型'}, ['yacinelearning','alexinexxx']),
}
REL={'直接认识+关系好的':4,'直接认识但不熟':2.5,'有connection的':2,'完全不认识':0,'':0}
VA={'互粉':1.5,'仅我关注':0.3,'仅TA关注我':0.5,'不在图谱':0}
def score(x,cid):
    title,bio_rules,meta,_=CAMP[cid]; b=(x['bio']+' '+x['name']+' '+x['handle']).lower(); s=0; why=[]
    for pat,w in bio_rules:
        ms=set(m.group(0) for m in re.finditer(pat,b)); 
        if ms: s+=w*min(len(ms),3); why+=sorted(ms)[:3]
    for t,w in meta.get('themes',{}).items():
        if t in x['themes']: s+=w; why.append('主题:'+t)
    pw=meta.get('personas',{}).get(x['personas'],0)
    if pw: s+=pw; why.append('人设:'+x['personas'])
    if x['track'] and re.search(meta['track'],x['track']): s+=3; why.append('10/19赛道:'+x['track'])
    bio_hit=any(re.search(pat,b) for pat,_ in bio_rules)
    track_hit=bool(x['track'] and re.search(meta['track'],x['track']))
    if cid==1 and not bio_hit and not track_hit and not (x['personas'] in('benchmarker','model_analyst') and x['bio'].strip()): return 0,[]
    if cid!=1 and not bio_hit and not track_hit: return 0,[]
    if cid==6:
        tool=re.search(bio_rules[1][0],b); role=re.search(r'maintainer|creator|founder|co-?founder|building|designing|lead|head of|ceo|cto|devrel|developer advocate|official|the (unified|home)|we ',b)
        if not (tool or track_hit or re.search(r'\bcli\b|coding agent|agent framework|ai coding|code editor|\bide\b|autonomous coding|agentic coding|agent harness',b) or (x['personas']=='coding_power_user' and 'agentic_coding' in x['themes'])): return 0,[]
    if s==0: return 0,[]
    s+=REL.get(x['rel'],0)+VA.get(x['va'],0)+(1 if x['official'] in('MiniMax互关','互粉') else 0)+min(math.log10(max(x['followers'],1)),6)*0.6+min(x['mx_posts'],10)*0.1
    return s,why
BLOCK={'minimax_ai','hailuo_ai','minimaxagent','deepseek_ai','zai_org','kimi_moonshot','alibaba_qwen','qwen','mistralai','openai','anthropicai','googledeepmind','xai','coinbureau','meta','ai21labs','cohere','sea_snell','yifeizhou02'}
SEED6=[('opencode','OpenCode'),('cline','Cline'),('kilocode','Kilo Code'),('roo_code','Roo Code'),('openhandsdev','OpenHands'),('factoryai','Factory / Droid'),('charmcli','Charm / Crush'),('continuedev','Continue'),('zeddotdev','Zed'),('openrouter','OpenRouter'),('requestyai','Requesty'),('yetone','avante.nvim 维护者'),('jason_young1231','CC Switch 维护者'),('lukeparkerdev','OpenCode 维护者'),('trae_ai','Trae'),('boltdotnew','Bolt'),('aider_ai','Aider'),('goose_oss','Goose (Block)'),('vllm_project','vLLM'),('ollama','Ollama')]
for h,label in []:
    x=rec(h); x['src'].add('C6 种子清单'); x['bio']=x['bio'] or (label+'（种子清单，handle 待核）'); x['name']=x['name'] or label
ORG_H={'arena','artificialanlys','openrouter','opencode','cline','kilocode','openhandsdev','unslothai','vllm_project','ollama','mtslive','bai_agi','miaai_lab','theturingpost','togethercompute','huggingmodels','commandcodeai','bridgemindai','thehypedotnews','vision_ia','roo_code','factoryai','charmcli','continuedev','zeddotdev','requestyai','trae_ai','boltdotnew','aider_ai','goose_oss','agtpinsights','digitalocean','vercel_dev','gmi_cloud','novita_labs','orcarouter','nousresearch','kimmonismus','rohanpaul_ai','maxforai','tokengremlin','yume_arasaki','zhihufrontier','explorax_','hasantoxr','ai_for_success','thelighthouse','astralmatrix','rails','statswire','browser_use','gradient_hq','arikalabs','capybara_ai','alignment_lab','repojournal','buildfastwithai','stretchcloud','108','sasuke___420'}
ORG_RE=re.compile(r"\bofficial\b|\bwe'?re\b|\bwe are\b|\bour (mission|team|platform|api|models?)\b|\bwe (build|help|make|surface|find|measure|accelerate)\b|the (unified|home|leading|first|best|open)|\bplatform for\b|\bhiring\b|\bjoin us\b|newsletter|daily (ai|news)|\bpodcast\b|\bmedia\b|\bcommunity for\b|\bstartup studio\b|\binc\.?\b|\bllc\b|^(the )?[a-z0-9 .-]+ (ai|labs?|project|cloud|team)$|ai news|breaking news|aggregat|\bupdates? on\b|open.?source (library|framework|platform)",re.I)
EXEC_RE=re.compile(r"\b(ceo|cto|coo|cfo|cpo|cmo|chief [a-z]+ officer|president|vice president|\bvp\b|svp|evp|head of|general partner|managing (partner|director)|angel investor|investor|venture|\bvc\b|board member|chairman|executive|exec\b|director of)\b",re.I)
def is_org(x):
    b=(x['bio'] or ''); n=(x['name'] or '')
    if x['handle'] in ORG_H or x['personas'] in('vendor','distribution') or x['excl']=='vendor_account': return True
    if not b.strip() and x['followers']>50000: return True
    if re.search(r'\b(ai|labs?|inc|hq|official|team|project|cloud|news|daily|post|research)\b',n,re.I) and not re.search(r"\b(engineer|dev|phd|student|researcher|scientist|building|i am|i'm|my )\b",b,re.I) and re.search(ORG_RE,b): return True
    return bool(re.search(ORG_RE,b)) and not re.search(r"\b(i'm|i am|my |me\b|engineer|developer|phd|student|researcher|scientist|maintainer|building|indie|solo)",b,re.I)
def is_exec(x):
    b=x['bio'] or ''
    if re.search(EXEC_RE,b): return True
    if re.search(r'\b(founder|co-?founder|cofounder)\b',b,re.I) and x['followers']>150000: return True
    return False
PER=30
used=collections.Counter(); result={}
for cid in CAMP:
    title,_,_,pins=CAMP[cid]; cand=[]
    for h,x in P.items():
        if x['excl']=='minimax_side_person': continue
        if is_org(x) or is_exec(x): continue
        if h in BLOCK or re.search(r'crypto|web3|solana|bitcoin|\bbtc\b|airdrop|defi|\bnft\b|#tron|onchain|memecoin',(x['bio']+x['name']).lower()): continue
        if cid!=6 and (x['excl']=='vendor_account' or x['personas']=='vendor'): continue
        s,why=score(x,cid)
        if h in pins: s+=100; why=['你点名']+why
        if s>0: cand.append((s-used[h]*2.5,h,why))
    cand.sort(reverse=True); pick=cand[:PER]
    for s,h,why in pick: used[h]+=1
    result[cid]={'title':title,'people':[{'rank':i+1,'handle':h,'name':P[h]['name'],'followers':P[h]['followers'],'rel':P[h]['rel'] or '—','va':P[h]['va'],'official':P[h]['official'] or '—','src':'/'.join(sorted(P[h]['src'])),'why':'、'.join(dict.fromkeys(why))[:120],'bio':P[h]['bio'][:140],'score':round(s,1)} for i,(s,h,why) in enumerate(pick)]}
json.dump(result,open(OUT/'campaign-sourcing.json','w'),ensure_ascii=False,indent=1)
md=['# 7 个 X Campaign 人选（每个 30 人，个人账号，已刷掉机构号/官方号/高管）— 2026-10-19','','来源：互粉名单（你的关系标注）、KOL Radar 08 全量账号池 + 01 Outreach、你本人互粉图谱（AI/开源 1,243 人）、10/19 outreach 名单、10/9 tpot 候选。打分 = 关键词匹配（bio/主题/人设/赛道）+ 关系加权（直接认识+关系好的 > 直接认识但不熟 > 有connection）+ 本人互粉 + 粉丝量对数。同一人最多跨 2 个 campaign，重复会被降权。**赵晨阳**在所有数据源里都查不到 handle，C5 里按名字留位。','']
for cid,r in result.items():
    md+=['## '+r['title'],'','| # | 账号 | 粉丝 | 你的关系 | 本人互粉 | 官号关系 | 为什么匹配 | 来源 |','|---|---|---|---|---|---|---|---|']
    for p in r['people']: md.append(f"| {p['rank']} | [@{p['handle']}](https://x.com/{p['handle']}) {p['name']} | {p['followers']:,} | {p['rel']} | {p['va']} | {p['official']} | {p['why']} | {p['src']} |")
    if cid==5: md.append('| 21 | 赵晨阳（待补 handle） | — | 你点名 | — | — | 你在 C5 点名 | 用户 |')
    md.append('')
open(OUT/'CAMPAIGN-SOURCING.zh-CN.md','w').write('\n'.join(md))
for cid,r in result.items(): print(r['title']); print('   ',', '.join(p['handle'] for p in r['people']))
print('overlap',sum(1 for h,c in used.items() if c>1))
