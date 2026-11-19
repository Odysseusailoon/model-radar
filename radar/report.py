"""Deterministic reports. Source statements remain explicitly unverified."""
from __future__ import annotations

import csv
import html
import io
from collections import Counter


def summary(run):
    return {k: run.get(k) for k in ("id", "status", "started_at", "completed_at", "requests_used", "attempts")} | {
        "signal_count": len(run["signals"]), "new_signal_count": sum(s.get("is_new", True) for s in run["signals"]),
        "entity_count": len(run["entities"]),
        "source_status": dict(Counter(c["status"] for c in run["coverage"])), "options": run["options"]}


def markdown(run):
    names = {e["id"]: e["name"] for e in run["entities"]}
    clean = lambda text: html.escape(" ".join(str(text).split())).replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")
    lines = ["# Inference Radar", "", f"Window: {run['options']['since']} → {run['options']['until']} (end exclusive).",
             f"Run: `{run['id']}` · Status: **{run['status']}** · {len(run['signals'])} unique observations.", "",
             "Counts describe this bounded sample, not total market volume. Social posts and performance claims are unverified. "
             "A model repository update may only change metadata. Open weights does not establish an open-source license.", "",
             "## Collection coverage", "", "| Entity | Source | Status | Pages | Observations | Gap |", "|---|---|---|---:|---:|---|"]
    for c in run["coverage"]:
        gap = c["error"] or ("page cap reached" if c["truncated"] else "")
        if c["invalid_records"]:
            gap += f"; {c['invalid_records']} malformed/undated records excluded"
        lines.append(f"| {clean(names[c['entity_id']])} | {c['source']} | {c['status']} | {c['pages']} | {c['fetched']} | {clean(gap)} |")
    lines += ["", "## Evidence", ""]
    for s in run["signals"]:
        lines += [f"### {clean(s['title'][:180])}", "",
                  f"{', '.join(names[i] for i in s['entity_ids'])} · {s['event_kind']} · {s['published_at']}",
                  f"[Original source]({s['url']}) · `{s['evidence_kind']}` · {'New observation' if s.get('is_new', True) else 'Previously observed'}",
                  "Topic hints: " + (", ".join(s.get("topic_tags", [])) or "uncategorized"), ""]
        if s["source"] == "huggingface":
            m = s["metadata"]
            lines += [f"License metadata: {clean(m.get('license', 'unknown'))}; gated: {m.get('gated', 'unknown')}; "
                      f"weight files listed: {m.get('weight_files_listed', False)}. License not independently reviewed.", ""]
        lines += ["> " + clean(s["text"][:1200]), ""]
    if not run["signals"]:
        lines.append("No observations in the returned sample. Check collection coverage before interpreting this as no activity.")
    return "\n".join(lines) + "\n"


def csv_export(run):
    stream = io.StringIO()
    fields = ["id", "source", "entity_ids", "event_kind", "evidence_kind", "topic_tags", "published_at", "title", "url"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for s in run["signals"]:
        row = {k: ",".join(s.get(k, [])) if isinstance(s.get(k), list) else s.get(k, "") for k in fields}
        # Spreadsheet programs interpret leading formula characters even in quoted CSV cells.
        row = {k: "'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()}
        writer.writerow(row)
    return stream.getvalue()
