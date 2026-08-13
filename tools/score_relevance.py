"""Score a following list for relevance to one outreach campaign, with a
per-person reason. Campaign-agnostic: the whole system prompt (company brief,
tier rubric, category keys) lives in <campaign>/scoring-prompt.md.

Every account with a bio is judged -- no keyword prefilter, because bios like
"Professor at MIT" carry no robotics keyword yet belong on the list. Batched
because the bios are one-liners; the batch is order-locked and handle-checked
so a mis-aligned reply is dropped rather than silently mis-attributed.

Judgments cache to <campaign>/judgments.json, so re-runs only pay for new
accounts and a second source list reuses everything already judged.

Run:
    .venv/bin/python tools/score_relevance.py <followings.json> --campaign campaigns/<name> [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.llm import first_text  # noqa: E402

BATCH = 15
WORKERS = 6


def _extract_json_array(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("no JSON array in reply")
    blob = text[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # Bios contain stray backslashes, and the model copies them through as
        # invalid escapes (\_ , \d ...). Escape any backslash not starting a
        # legal JSON escape, then parse again.
        return json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", blob))


def judge(client, model, system: str, batch: list[dict]) -> dict[str, dict]:
    payload = [{"handle": u["handle"], "name": u["name"],
                "followers": u["followers"], "bio": u["bio"][:400]} for u in batch]
    msg = client.messages.create(
        model=model, max_tokens=6000, system=system,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    # The gateway spends 1.5-4k tokens thinking before answering, so a batch can
    # run out of budget mid-array. Split rather than lose the batch silently.
    if msg.stop_reason == "max_tokens":
        if len(batch) == 1:
            raise ValueError("single-account reply still truncated")
        mid = len(batch) // 2
        out = judge(client, model, system, batch[:mid])
        out.update(judge(client, model, system, batch[mid:]))
        return out

    rows = _extract_json_array(first_text(msg))
    want = {u["handle"].lower() for u in batch}
    out = {}
    for r in rows:
        h = str(r.get("handle", "")).lstrip("@")
        if h.lower() not in want:
            continue  # hallucinated or drifted handle -> drop, don't mis-attribute
        out[h.lower()] = {
            "handle": h,
            "tier": int(r.get("tier", 0) or 0),
            "category": str(r.get("category", "other") or "other"),
            "reason": str(r.get("reason", "") or "").strip(),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--campaign", required=True,
                    help="campaign dir holding scoring-prompt.md; judgments cache lands there too")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    camp = Path(a.campaign)
    system = (camp / "scoring-prompt.md").read_text()
    cache_file = camp / "judgments.json"

    users = json.loads(Path(a.infile).read_text())["followings"]
    users = [u for u in users if u["bio"].strip()]
    if a.limit:
        users = users[: a.limit]

    cache: dict[str, dict] = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    todo = [u for u in users if u["handle"].lower() not in cache]
    print(f"{len(users)} with bio | cached {len(users) - len(todo)} | to judge {len(todo)}", flush=True)

    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key, base_url=s.anthropic_base_url,
                                 timeout=90.0, max_retries=3)
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(judge, client, s.classifier_model, system, b): b for b in batches}
        for fut in as_completed(futs):
            try:
                cache.update(fut.result())
            except Exception as exc:  # noqa: BLE001
                print(f"  batch failed: {type(exc).__name__}: {exc}", flush=True)
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(batches)} batches, {len(cache)} judged", flush=True)
                cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    tiers: dict[int, int] = {}
    for v in cache.values():
        tiers[v["tier"]] = tiers.get(v["tier"], 0) + 1
    print(f"\njudged {len(cache)} total -> {cache_file}")
    for t in sorted(tiers, reverse=True):
        print(f"  tier {t}: {tiers[t]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
