"""Build a KOL shortlist from the *overlap* of who a set of seed accounts follow.

Idea: an account followed by many of these hand-curated lab/researcher accounts
is almost certainly a credible voice in the space. We union the followings of
all SEED accounts, count how many distinct seeds follow each target, and keep
the targets crossing a threshold (default: more than 3 seeds).

Data sources, in priority order, per seed:
  1. A per-seed cache file under CACHE_DIR (scratchpad) — written on first fetch.
  2. The legacy kol-candidates.json, which stores, for the 4 original seeds,
     every account they follow (reconstructable from each candidate's
     `followed_by` list). Lets us avoid re-paying for those 4.
  3. Live twitterapi.io via XDataClient — only for seeds missing from 1 and 2.
     Requires TWITTERAPI_KEY in the environment (or .env).

Run:
    TWITTERAPI_KEY=... .venv/bin/python tools/build_kol_list.py
Offline (no key) still works for whatever is already cached, and prints exactly
which seeds still need a live fetch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEEDS = [
    "Kimi_Moonshot", "MiniMax_AI", "crystalsssup", "Zai_org",
    "willccbb", "eliebakouch", "SonglinYang4", "yacinelearning",
]
THRESHOLD = 4  # "more than 3 of those people" → followed by >= 4 seeds
LEGACY_FILE = ROOT / "kol-candidates.json"
CACHE_DIR = Path(os.getenv("KOL_CACHE_DIR", "/tmp/kol-followings-cache"))
OUT_JSON = ROOT / "kol-candidates-8.json"

# The seeds are themselves accounts; never recommend a seed as a KOL. Also drop
# obvious first-party product accounts so competitor marketing isn't scored as
# independent KOL signal.
EXCLUDE = {s.lower() for s in SEEDS} | {
    "kimi_moonshot", "minimax_ai", "zai_org", "deepseek_ai", "alibaba_qwen",
    "openai", "anthropicai", "googledeepmind", "moonshotai",
}


def _load_env_key() -> str | None:
    key = os.getenv("TWITTERAPI_KEY")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("TWITTERAPI_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _seed_cache_from_legacy() -> None:
    """Reconstruct the 4 original seeds' followings from kol-candidates.json and
    write them to the cache, so we never re-fetch them."""
    if not LEGACY_FILE.exists():
        return
    legacy = json.loads(LEGACY_FILE.read_text())
    per_seed: dict[str, list[dict]] = {}
    for c in legacy.get("candidates", []):
        rec = {"handle": c["handle"], "name": c.get("name", ""),
               "followers": c.get("followers", 0), "bio": c.get("bio", "")}
        for s in c.get("followed_by", []):
            per_seed.setdefault(s, []).append(rec)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for seed, recs in per_seed.items():
        f = CACHE_DIR / f"{seed}.json"
        if not f.exists():
            f.write_text(json.dumps(recs, ensure_ascii=False))
            print(f"  seeded cache from legacy: {seed} ({len(recs)} followings)")


def _fetch_followings(seed: str, api_key: str) -> list[dict]:
    from app.xclient import XDataClient
    client = XDataClient(api_key=api_key)
    out = []
    for author in client.user_followings(seed, max_pages=25):
        out.append({"handle": author.handle, "name": author.name,
                    "followers": author.followers, "bio": author.bio})
    return out


def load_seed_followings(seed: str, api_key: str | None) -> list[dict] | None:
    cache = CACHE_DIR / f"{seed}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    if not api_key:
        return None
    print(f"  fetching followings for @{seed} (live)…")
    recs = _fetch_followings(seed, api_key)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(recs, ensure_ascii=False))
    print(f"    got {len(recs)}")
    return recs


def main() -> int:
    api_key = _load_env_key()
    _seed_cache_from_legacy()

    followings: dict[str, list[dict]] = {}
    missing = []
    for seed in SEEDS:
        recs = load_seed_followings(seed, api_key)
        if recs is None:
            missing.append(seed)
        else:
            followings[seed] = recs

    print(f"\nSeeds with data: {len(followings)}/{len(SEEDS)}")
    if missing:
        print(f"Seeds STILL NEEDING a live fetch (need TWITTERAPI_KEY): {', '.join(missing)}")

    # Aggregate: per target handle, which seeds follow it + best metadata.
    agg: dict[str, dict] = {}
    for seed, recs in followings.items():
        for r in recs:
            h = (r.get("handle") or "").lower()
            if not h or h in EXCLUDE:
                continue
            a = agg.setdefault(h, {"handle": r["handle"], "name": r.get("name", ""),
                                   "followers": 0, "bio": r.get("bio", ""), "followed_by": set()})
            a["followed_by"].add(seed)
            # keep the richest metadata we saw
            a["followers"] = max(a["followers"], r.get("followers", 0) or 0)
            if len(r.get("name", "")) > len(a["name"]):
                a["name"] = r["name"]
            if len(r.get("bio", "")) > len(a["bio"]):
                a["bio"] = r["bio"]

    kept = [a for a in agg.values() if len(a["followed_by"]) >= THRESHOLD]
    kept.sort(key=lambda a: a["followers"], reverse=True)

    out = {
        "seeds": SEEDS,
        "seeds_with_data": sorted(followings),
        "seeds_missing": missing,
        "threshold": THRESHOLD,
        "per_account": {s: len(followings.get(s, [])) for s in SEEDS},
        "candidates": [
            {**a, "followed_by": sorted(a["followed_by"]),
             "followed_by_count": len(a["followed_by"])}
            for a in kept
        ],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nKept {len(kept)} accounts followed by >= {THRESHOLD} of "
          f"{len(followings)} available seeds → {OUT_JSON.name}")

    print(f"\n{'#':>3}  {'handle':<22}{'followers':>11}  #seeds  name")
    for i, a in enumerate(kept[:60], 1):
        print(f"{i:>3}  @{a['handle']:<21}{a['followers']:>11,}  "
              f"{len(a['followed_by']):>5}   {a['name'][:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
