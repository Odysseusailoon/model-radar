"""Read-only Ox Alpha pre-reveal partner audit; resumable bounded searches."""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.xclient import XDataClient
OUT=ROOT/'reports/2026-09-22-flash-synthesis/evidence/ox-alpha'
OUT.mkdir(parents=True,exist_ok=True)
q=[]
def add(tag,query,mode='Latest',pages=3):
 q.append(dict(tag=tag,query=query+' -filter:retweets',mode=mode,max_pages=pages))
OX='("ox alpha" OR "ox-alpha" OR "ox_alpha")'
WINDOW='since:2026-08-19 until:2026-08-27'
add('vercel_ox',f'{OX} (vercel OR "ai gateway" OR "fx.sh" OR "from:vercel" OR "from:rauchg") {WINDOW}',pages=3)
add('vercel_official',f'(from:vercel OR from:rauchg OR from:cramforce) (ox OR GLM OR stealth OR blackbox) {WINDOW}',pages=3)
add('nous_hermes',f'{OX} (from:NousResearch OR from:Teknium OR from:HermesAgent OR from:hermes_agent) {WINDOW}',pages=3)
add('other_official',f'{OX} (from:AskVenice OR from:mercury__agent OR from:pidotdev OR from:perchai OR from:perch_ai OR from:aihubmix OR from:kilocode OR from:cline OR from:opencode OR from:OpenRouter) {WINDOW}',pages=5)
add('partner_announcements',f'{OX} (available OR launch OR integrated OR integration OR provider OR gateway OR supported OR 上线 OR 接入 OR 免费) {WINDOW}',mode='Top',pages=5)
add('perch_mercury',f'{OX} (perch OR mercury OR aihubmix OR nano OR chutes OR requesty) {WINDOW}',pages=3)
add('more_official',f'{OX} (from:CommandCodeAI OR from:MyTabulon OR from:cencori OR from:perchai OR from:perch_ai OR from:perchai_app OR from:PerchAIApp) {WINDOW}',pages=4)
add('command_perch',f'{OX} ("command code" OR commandcode OR "perch ai" OR perchai) {WINDOW}',pages=3)
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
