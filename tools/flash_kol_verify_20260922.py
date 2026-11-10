"""Verify the proposed Ox Alpha -> M3.1 Flash outreach names against live X data.

Two jobs:
  1. For each named handle, did they actually post about Ox Alpha / GLM Flash,
     and do they have any MiniMax history? (batched from: queries)
  2. Bottom-up: who actually drove the Ox Alpha benchmark / identity / skeptic
     conversation, independent of the proposed list?

Resumable: tags already 'ok' in queries.json are skipped.
Usage: .venv/bin/python tools/flash_kol_verify_20260922.py
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.xclient import XDataClient

OUT = ROOT / 'reports/2026-09-22-flash-kol/evidence'
OUT.mkdir(parents=True, exist_ok=True)

NAMED = ["winkey_h","davis7","MiaAI_lab","kilocode","Prathkum","thdxr",
         "OpenRouterAI","opencode","ArtificialAnlys","arena","TheTuringPost",
         "NousResearch","AndrewCurran_","spdustin","AGTPinsights","kimmonismus",
         "bytebot","openhandsdev","eliebakouch","alexellisuk","patrickc"]

q = []
def add(tag, query, mode='Latest', pages=3):
    q.append(dict(tag=tag, query=query + ' -filter:retweets', mode=mode, max_pages=pages))

OX = '("ox alpha" OR "ox-alpha" OR "ox_alpha")'
FLASH = '("GLM-5.3-Flash" OR "GLM 5.3 Flash" OR "glm-5.3-flash")'
MX = '(minimax OR hailuo OR "M2.5" OR "M2.7" OR "M3.1" OR "MiniMax-M3" OR "MiniMax M3")'

# --- 1. per-handle verification, batched 6 at a time ------------------------
for i in range(0, len(NAMED), 6):
    grp = NAMED[i:i+6]
    frm = '(' + ' OR '.join('from:' + h for h in grp) + ')'
    add(f'named_ox_{i//6}',  f'{frm} ({OX} OR {FLASH} OR DeepSWE OR stealth) since:2026-08-15 until:2026-09-23', 'Latest', 3)
    add(f'named_mx_{i//6}',  f'{frm} {MX} since:2026-03-01 until:2026-09-23', 'Latest', 4)

# --- 2. MiniMax official timeline (amplification edges) ---------------------
add('mx_official', '(from:MiniMax_AI OR from:MiniMax__AI) since:2026-03-01 until:2026-09-23', 'Latest', 8)

# --- 3. bottom-up Ox Alpha conversation ------------------------------------
add('ox_benchmark', f'{OX} (DeepSWE OR "SWE-bench" OR swebench OR benchmark OR eval OR "pass rate" OR tasks OR score OR "113") since:2026-08-19 until:2026-09-10', 'Top', 5)
add('ox_identity',  f'{OX} (tokenizer OR "which lab" OR whose OR identity OR GLM OR zhipu OR "z.ai" OR deepseek OR minimax OR qwen OR guess OR reveal) since:2026-08-19 until:2026-09-10', 'Top', 5)
add('ox_skeptic',   f'{OX} (overhyped OR "not that good" OR worse OR bad OR fails OR failed OR disappointing OR mid OR css OR "sample size" OR variance OR "tool call") since:2026-08-19 until:2026-09-10', 'Top', 4)
add('ox_daily',     f'({OX} OR {FLASH}) ("daily driver" OR "using it" OR "been using" OR workflow OR agent OR opencode OR cline OR kilo OR roo) since:2026-08-19 until:2026-09-23', 'Top', 4)
add('ox_latest',    f'{OX} since:2026-08-19 until:2026-09-10', 'Latest', 6)

# --- 4. fact checks on claims in the proposal ------------------------------
add('flashx',   '("GLM-5.3-FlashX" OR "GLM 5.3 FlashX" OR "flashx") since:2026-09-10 until:2026-09-23', 'Top', 3)
add('m31flash', '("M3.1 Flash" OR "MiniMax M3.1" OR "M3.1-Flash" OR "MiniMax-M3.1") since:2026-07-01 until:2026-09-23', 'Top', 3)

key = None
for line in (ROOT / '.env').read_text().splitlines():
    if line.startswith('TWITTERAPI_KEY='):
        key = line.split('=', 1)[1].strip().strip('"').strip("'")
if not key: raise SystemExit('TWITTERAPI_KEY missing')
client = XDataClient(api_key=key)

mf = OUT / 'queries.json'
manifest = json.loads(mf.read_text()) if mf.exists() else []
done = {x['tag'] for x in manifest if x.get('status') == 'ok'}
for item in q:
    if item['tag'] in done: continue
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
                             collected_at=stamp))
        item.update(status='ok', count=len(rows), collected_at=stamp)
    except Exception as e:
        item.update(status='error', error=f'{type(e).__name__}: {e}', count=len(rows), collected_at=stamp)
    (OUT / (item['tag'] + '.json')).write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    manifest = [x for x in manifest if x['tag'] != item['tag']] + [item]
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(item['tag'], item['status'], len(rows), flush=True)
print('COMPLETE', flush=True)
