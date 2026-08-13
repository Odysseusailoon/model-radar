"""List an account's mutuals (follow-each-other) filtered to the AI / open-source
tech crowd, ranked by follower count.

mutuals = (accounts I follow) ∩ (accounts that follow me).

Both lists are fetched once and cached under CACHE_DIR so re-runs / filter tweaks
are free. On the free tier (1 req/5s, 200 users/page) a 23k-follower account is
~115 pages ≈ 10 min for the followers side.

Run:
    TWITTERAPI_KEY=... .venv/bin/python tools/mutuals.py [screen_name]
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if len(sys.argv) < 2:
    raise SystemExit("usage: tools/mutuals.py <screen_name>")
HANDLE = sys.argv[1].lstrip("@")
CACHE_DIR = Path(os.getenv("MUTUALS_CACHE_DIR", "/tmp/mutuals-cache"))
OUT_MD = ROOT / f"{HANDLE.lower()}-mutuals.md"
OUT_JSON = ROOT / f"{HANDLE.lower()}-mutuals.json"

# AI / OSS / tech-community heuristic over name+bio. Word boundaries on the short
# risky tokens (ai, ml, rl, cv, hf, oss, gpu) so "email"/"html" don't match.
_EN = re.compile(
    r"\b(ai|ml|llm|nlp|rl|cv|gpu|cuda|oss|hf|agent|agents|agentic|research|researcher|"
    r"phd|professor|scientist|neural|transformer|diffusion|gpt|inference|pretrain|"
    r"fine[- ]?tun|embedding|rag|multimodal|generative|genai|open[- ]?source|opensource|"
    r"github|developer|engineer|software|pytorch|tensorflow|jax|hugging ?face|"
    r"founder|cto|compiler|kernel|robot|robotics|deep learning|machine learning|"
    r"reinforcement|quant|hacker|maintainer|infra|distributed|systems|"
    # programming / builder signals — catches OSS folks whose bios never say "AI"
    r"programming|programmer|coder|codes?|coding|builder|builds|building|"
    r"creator|contributor|hacking|linux|kubernetes|k8s|redis|postgres|database|"
    r"backend|frontend|full[- ]?stack|devops|sre|rust|golang|typescript)\b",
    re.I,
)
_CN = re.compile(
    r"(开源|大模型|模型|算法|研究|工程师|开发|深度学习|机器学习|人工智能|智能体|"
    r"训练|推理|博士|实验室|神经|生成式|智能)"
)


def _is_ai_oss(rec: dict) -> bool:
    text = f"{rec.get('name', '')} {rec.get('bio', '')}"
    return bool(_EN.search(text) or _CN.search(text))


def _key() -> str:
    k = os.getenv("TWITTERAPI_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("TWITTERAPI_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("TWITTERAPI_KEY not set")


def _fetch(kind: str, client, handle: str) -> list[dict]:
    """kind in {'followings','followers'}; cached per handle."""
    cache = CACHE_DIR / f"{handle}.{kind}.json"
    if cache.exists():
        recs = json.loads(cache.read_text())
        print(f"  {kind}: {len(recs)} (cached)")
        return recs
    fn = client.user_followers if kind == "followers" else client.user_followings
    recs = [{"handle": a.handle, "name": a.name, "followers": a.followers, "bio": a.bio}
            for a in fn(handle, max_pages=200)]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(recs, ensure_ascii=False))
    print(f"  {kind}: {len(recs)} (fetched)")
    return recs


def main() -> int:
    from app.xclient import XDataClient
    client = XDataClient(api_key=_key())

    print(f"@{HANDLE}: fetching followings + followers …")
    followings = _fetch("followings", client, HANDLE)
    followers = _fetch("followers", client, HANDLE)

    # Mutuals = intersection by handle. Keep the richest metadata across sources.
    fset = {r["handle"].lower() for r in followers if r.get("handle")}
    best: dict[str, dict] = {}
    for r in followings:
        h = (r.get("handle") or "").lower()
        if h and h in fset:
            best[h] = r
    for r in followers:  # enrich follower counts / bios
        h = (r.get("handle") or "").lower()
        if h in best and (r.get("followers", 0) or 0) > (best[h].get("followers", 0) or 0):
            best[h] = r
    mutuals = list(best.values())
    print(f"\nmutuals total: {len(mutuals)}")

    ai = [m for m in mutuals if _is_ai_oss(m)]
    ai.sort(key=lambda m: m.get("followers", 0) or 0, reverse=True)
    print(f"AI/OSS-filtered mutuals: {len(ai)}")

    OUT_JSON.write_text(json.dumps(
        {"handle": HANDLE, "mutuals_total": len(mutuals), "ai_oss_count": len(ai), "mutuals": ai},
        ensure_ascii=False, indent=2))

    lines = [f"# @{HANDLE} mutuals — AI / 开源技术社区(按粉丝排序)",
             f"\n互粉总数 **{len(mutuals)}**,其中 AI/开源相关 **{len(ai)}**。（关键词启发式,可再人工微调)\n",
             "| # | handle | followers | name — bio |", "|--|--|--|--|"]
    for i, m in enumerate(ai, 1):
        bio = (m.get("bio") or "").replace("\n", " ").replace("|", "/")[:80]
        lines.append(f"| {i} | @{m['handle']} | {m.get('followers', 0):,} | {m.get('name', '')[:24]} — {bio} |")
    OUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUT_MD.name} + {OUT_JSON.name}")

    print(f"\n{'#':>3}  {'handle':<22}{'followers':>11}  name")
    for i, m in enumerate(ai[:50], 1):
        print(f"{i:>3}  @{m['handle']:<21}{m.get('followers', 0):>11,}  {m.get('name', '')[:34]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
