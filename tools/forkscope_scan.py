"""Scan X for the "forking paths / agent failure attribution" research field:
Goodfire forking-paths work, counterfactual replay, agent failure analysis,
entropy-based critical steps in agentic RL (ARPO/AEPO/Tree-GRPO), SGLang
RadixAttention prefix caching, sfcompute givemeanode, self-improving agents.

Run:
    .venv/bin/python tools/forkscope_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.xclient import XDataClient

OUT = ROOT / "forkscope-field-tweets-2026-08-31.json"

QUERIES = {
    # The original research this reproduces
    "forking_paths": '("forking paths" OR "forking tokens" OR "fork tokens") (LLM OR token OR model OR sampling OR Goodfire OR interpretability) -filter:retweets',
    "goodfire": '(goodfire OR Bigelow) (forking OR fork OR paths OR interpretability OR "change point") -filter:retweets',
    # Agent failure analysis / attribution
    "agent_failure": '("agent failure" OR "agent failures" OR "failure attribution" OR "error attribution") (LLM OR agent OR agentic OR trajectory OR step) -filter:retweets',
    "agent_debug": '(agent OR agentic) (observability OR tracing OR "root cause" OR debug) (LLM OR trajectory OR "tool call") (failure OR fails OR error) -filter:retweets',
    # Counterfactual replay / critical decision steps
    "counterfactual": '(counterfactual) (agent OR rollout OR replay OR trajectory OR LLM) -filter:retweets',
    "critical_steps": '("critical step" OR "critical steps" OR "critical tokens" OR "decision point" OR "pivotal token" OR "pivotal tokens") (agent OR LLM OR RL OR trajectory) -filter:retweets',
    # Entropy-based RL methods the post argues against
    "entropy_rl": '("high-entropy tokens" OR "high entropy tokens" OR "token entropy") (RL OR reinforcement OR agentic OR reasoning) -filter:retweets',
    "arpo_aepo": '(ARPO OR AEPO OR "Tree-GRPO" OR "tree GRPO") (RL OR agent OR rollout OR entropy OR policy) -filter:retweets',
    # Infra pieces
    "sglang_radix": '(RadixAttention OR "radix attention" OR "prefix caching" OR "prefix cache") (sglang OR vllm OR agent OR replay OR rollout) -filter:retweets',
    "sfcompute": '(sfcompute OR givemeanode OR "give me a node") -filter:retweets',
    # Self-improvement loop
    "self_improve": '("self-improving agent" OR "self-improving agents" OR "recursive self-improvement" OR "self-improvement") (agent OR tool OR prompt OR LLM) -filter:retweets',
    "tool_desc": '("tool description" OR "tool descriptions" OR "prompt optimization") (agent OR MCP OR improve OR optimize OR rewrite) -filter:retweets',
}


def _key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TWITTERAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TWITTERAPI_KEY not set")


def main() -> int:
    client = XDataClient(api_key=_key())
    seen: dict[str, dict] = {}
    for tag, q in QUERIES.items():
        n0 = len(seen)
        try:
            for t in client.search_recent(q, max_pages=3):
                rec = seen.setdefault(t.id, {
                    "id": t.id,
                    "url": t.url or f"https://x.com/i/status/{t.id}",
                    "text": t.text,
                    "created": t.created_at.isoformat() if t.created_at else None,
                    "author": t.author.handle,
                    "author_name": t.author.name,
                    "followers": t.author.followers,
                    "likes": t.like_count,
                    "retweets": t.retweet_count,
                    "views": t.view_count,
                    "matched": [],
                })
                if tag not in rec["matched"]:
                    rec["matched"].append(tag)
        except Exception as exc:  # noqa: BLE001
            print(f"{tag}: ERROR {exc}")
        print(f"{tag}: +{len(seen) - n0} (total {len(seen)})", flush=True)

    tweets = sorted(seen.values(), key=lambda r: -(r.get("likes") or 0))
    OUT.write_text(json.dumps(tweets, ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT.name}: {len(tweets)}")
    for t in tweets[:40]:
        print(f"  ❤{t['likes']:>5} 👀{t.get('views') or 0:>8} @{t['author']:<18} {(t['text'] or '')[:110].replace(chr(10),' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
