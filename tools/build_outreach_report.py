"""Build an outreach shortlist for one campaign: PDF (Chrome headless) + a
Feishu-importable CSV.

Joins three inputs:
  <handle>-followings.json     the source following list (tools/fetch_followings.py)
  <campaign>/judgments.json    tier + category + reason per account (tools/score_relevance.py)
  --self-graph graph.json      optional: your own followings/followers (tools/fetch_graph.py)

With --self-graph, every person gets a relation column. It is four-state, not
a yes/no: 互粉 / 对方关注我 / 我已关注(未回关) / 无关系 -- warm-intro
sequencing depends on which one it is -- and everyone with an existing
relationship is pulled into a 优先触达 section at the front.

Feishu Base imports CSV/XLSX, never PDF, so both come out of one run.

Run:
    .venv/bin/python tools/build_outreach_report.py <followings.json> \
        --campaign campaigns/<name> [--self-graph me-graph.json --self-name MyHandle] \
        [--min-tier 2] [--pdf-min-tier 3]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import subprocess
from pathlib import Path

CHROME = os.environ.get(
    "CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

REL_ORDER = {"互粉": 0, "对方关注我": 1, "我已关注(未回关)": 2, "无关系": 3}

DEFAULT_TIER_BLURBS = {
    3: "命中公司核心技术或业务交集,或为直接的客户 / 合作 / 投资决策者。",
    2: "相邻领域从业者,可作为早期用户、候选人或传播节点。",
}


def relation(handle: str, my_following: set[str], my_followers: set[str]) -> str:
    h = handle.lower()
    fo, fr = h in my_following, h in my_followers
    if fo and fr:
        return "互粉"
    if fr:
        return "对方关注我"
    if fo:
        return "我已关注(未回关)"
    return "无关系"


def load(infile: str, camp: Path, min_tier: int, graph_file: str | None):
    src = json.loads(Path(infile).read_text())
    judg = json.loads((camp / "judgments.json").read_text())
    cfg = json.loads((camp / "config.json").read_text())
    cat_label = {c["key"]: c["label"] for c in cfg["categories"]}
    cat_order = [c["key"] for c in cfg["categories"]]
    if "other" not in cat_label:
        cat_label["other"] = "其他"
        cat_order.append("other")

    my_following: set[str] = set()
    my_followers: set[str] = set()
    if graph_file:
        g = json.loads(Path(graph_file).read_text())
        my_following = {u["handle"].lower() for u in g["followings"]}
        my_followers = {u["handle"].lower() for u in g["followers"]}

    rows = []
    for u in src["followings"]:
        j = judg.get(u["handle"].lower())
        if not j or j["tier"] < min_tier:
            continue
        rows.append({
            "name": u["name"] or u["handle"],
            "handle": u["handle"],
            "url": f"https://x.com/{u['handle']}",
            "followers": u["followers"],
            "tier": j["tier"],
            "category": j["category"] if j["category"] in cat_label else "other",
            "reason": j["reason"],
            "relation": (relation(u["handle"], my_following, my_followers)
                         if graph_file else ""),
            "bio": u["bio"],
        })
    rows.sort(key=lambda r: (-r["tier"],
                             cat_order.index(r["category"]),
                             REL_ORDER.get(r["relation"], 9),
                             -r["followers"]))
    return src["handle"], rows, judg, cfg, cat_label, cat_order


def write_csv(path: Path, rows: list[dict], cat_label: dict,
              self_name: str | None) -> None:
    # utf-8-sig: Feishu and Excel both need the BOM to read Chinese headers.
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        head = ["姓名", "X 账号", "链接", "粉丝数", "相关度", "分类", "相关性说明"]
        if self_name:
            head.append(f"与 {self_name} 关系")
        head.append("原始 bio")
        w.writerow(head)
        for r in rows:
            row = [r["name"], "@" + r["handle"], r["url"], r["followers"],
                   f"T{r['tier']}", cat_label[r["category"]], r["reason"]]
            if self_name:
                row.append(r["relation"])
            row.append(r["bio"].replace("\n", " "))
            w.writerow(row)


def _fmt(n: int) -> str:
    return f"{n:,}"


def build_html(source: str, rows: list[dict], judg: dict, total_src: int,
               pdf_min_tier: int, cfg: dict, cat_label: dict, cat_order: list,
               self_name: str | None, snap_date: str) -> str:
    t3 = [r for r in rows if r["tier"] == 3]
    t2 = [r for r in rows if r["tier"] == 2]
    mutual = [r for r in rows if r["relation"] == "互粉"]
    inbound = [r for r in rows if r["relation"] == "对方关注我"]
    # Anyone who already has a connection is actionable today, whatever their tier,
    # so they lead the document instead of being scattered through the categories.
    warm = sorted(mutual + inbound,
                  key=lambda r: (-r["tier"], REL_ORDER[r["relation"]], -r["followers"]))
    body_rows = [r for r in rows if r["tier"] >= pdf_min_tier]
    tier_blurbs = {int(k): v for k, v in cfg.get("tier_blurbs", {}).items()} or DEFAULT_TIER_BLURBS
    cats: dict[str, int] = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1

    def table(items: list[dict], show_tier: bool = False) -> str:
        # No category column: rows are already grouped under a category heading.
        # Column widths must sum to 100 with or without the relation column.
        th = ['<th class="w-name">人物</th><th class="w-num">粉丝</th>']
        if show_tier:
            th.append('<th class="w-tier">相关度</th>')
        if self_name:
            th.append('<th class="w-rel">与我关系</th>')
        th.append('<th class="w-why">相关性</th>')
        out = [f'<table><thead><tr>{"".join(th)}</tr></thead><tbody>']
        for r in items:
            rel = r["relation"]
            cls = {"互粉": "rel-mutual", "对方关注我": "rel-in",
                   "我已关注(未回关)": "rel-out"}.get(rel, "rel-none")
            tier_td = (f'<td class="tier">T{r["tier"]} · '
                       f'{html.escape(cat_label[r["category"]])}</td>') if show_tier else ""
            rel_td = (f'<td><span class="pill {cls}">{html.escape(rel)}</span></td>'
                      if self_name else "")
            out.append(
                "<tr>"
                f'<td class="name"><a href="{html.escape(r["url"])}">{html.escape(r["name"])}</a>'
                f'<span class="handle">@{html.escape(r["handle"])}</span></td>'
                f'<td class="num">{_fmt(r["followers"])}</td>'
                f"{tier_td}{rel_td}"
                f'<td class="why">{html.escape(r["reason"])}</td>'
                "</tr>")
        out.append("</tbody></table>")
        return "".join(out)

    def section(tier: int, items: list[dict], title: str, blurb: str) -> str:
        if not items:
            return ""
        parts = [f'<section class="tier"><h2><span class="tnum">T{tier}</span>{html.escape(title)}'
                 f'<span class="tcount">{len(items)} 人</span></h2>'
                 f'<p class="blurb">{html.escape(blurb)}</p>']
        for c in cat_order:
            grp = [r for r in items if r["category"] == c]
            if grp:
                parts.append(f'<h3>{html.escape(cat_label[c])} <span class="gcount">'
                             f'{len(grp)}</span></h3>{table(grp)}')
        parts.append("</section>")
        return "".join(parts)

    warm_block = (
        f'<section class="tier warm"><h2>优先触达 · 已有关系'
        f'<span class="tcount">{len(warm)} 人</span></h2>'
        f'<p class="blurb">这些人已经关注了 {html.escape(self_name or "")},可以直接私信,'
        f'不需要引荐。按相关度排序,跨分类合并。</p>{table(warm, show_tier=True)}</section>'
    ) if (self_name and warm) else ""

    catlines = "".join(
        f'<div class="statline"><span>{html.escape(cat_label[c])}</span>'
        f'<span class="dots"></span><span class="sv">{cats[c]}</span></div>'
        for c in cat_order if c in cats)

    # brief paragraphs come from the campaign author -- basic inline HTML
    # (<strong> etc.) is allowed, so they are inserted unescaped.
    brief = "".join(f"<p>{p}</p>" for p in cfg["company_brief"])
    sources_li = (f'<li>{html.escape(cfg["sources_note"])}</li>'
                  if cfg.get("sources_note") else "")

    if self_name:
        kpis = (f'<div class="kpi"><div class="v">{len(t3)}</div><div class="l">T3 强相关</div></div>'
                f'<div class="kpi"><div class="v">{len(t2)}</div><div class="l">T2 中相关</div></div>'
                f'<div class="kpi"><div class="v">{len(mutual)}</div><div class="l">与 {html.escape(self_name)} 互粉</div></div>'
                f'<div class="kpi"><div class="v">{len(inbound)}</div><div class="l">已关注 {html.escape(self_name)}</div></div>')
        ncols = 4
        howto = (f'<p style="font-size:8.4pt;color:var(--ink-2);margin:0 0 2mm">'
                 f'从「<strong>优先触达</strong>」开始——这些人已经关注了 {html.escape(self_name)},'
                 f'可以直接私信。标<strong>互粉</strong>的关系最强;<strong>对方关注我</strong>的'
                 f'对内容有兴趣但未建立双向关系,先互动几轮再开口。</p>'
                 f'<p style="font-size:8.4pt;color:var(--ink-2);margin:0">'
                 f'其余按分类顺序排列,同分类内已有关系优先、粉丝量次之,可直接顺序往下推。'
                 f'<strong>无关系</strong>的人需要引荐,或先以内容触达。</p>')
        rel_method = ('<li>「与我关系」由本人的关注 / 粉丝列表离线比对得出,四态区分,'
                      '非二值判断。</li>')
    else:
        kpis = (f'<div class="kpi"><div class="v">{len(t3)}</div><div class="l">T3 强相关</div></div>'
                f'<div class="kpi"><div class="v">{len(t2)}</div><div class="l">T2 中相关</div></div>')
        ncols = 2
        howto = ('<p style="font-size:8.4pt;color:var(--ink-2);margin:0">'
                 '按分类顺序排列,同分类内粉丝量优先,可直接顺序往下推。</p>')
        rel_method = ""

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(cfg["title"])}</title>
<style>
:root {{
  --ink:#16181c; --ink-2:#454a54; --ink-3:#7b8290; --rule:#dcdfe5;
  --ground:#ffffff; --band:#f5f6f8; --accent:#1f4e79;
}}
* {{ box-sizing:border-box; }}
@page {{ size:A4; margin:14mm 12mm 16mm; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"PingFang SC","Hiragino Sans GB","Helvetica Neue",Arial,sans-serif;
  font-size:9.2pt; line-height:1.5; -webkit-print-color-adjust:exact; print-color-adjust:exact;
}}
h1 {{ font-size:20pt; margin:0 0 2mm; letter-spacing:-.2pt; }}
.sub {{ color:var(--ink-3); font-size:9pt; margin:0 0 6mm; }}
.brief {{ background:var(--band); border-left:2.5pt solid var(--accent);
  padding:4mm 5mm; margin:0 0 6mm; }}
.brief h2 {{ font-size:11pt; margin:0 0 2mm; }}
.brief p {{ margin:0 0 2mm; color:var(--ink-2); }}
.brief p:last-child {{ margin-bottom:0; }}
.cols {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8mm; margin:0 0 6mm; }}
.col h3 {{ font-size:8pt; text-transform:uppercase; letter-spacing:.8pt;
  color:var(--ink-3); margin:0 0 2mm; font-weight:600; }}
.statline {{ display:flex; align-items:baseline; gap:1.5mm; font-size:8.6pt;
  padding:.7mm 0; border-bottom:.4pt dotted var(--rule); }}
.statline .dots {{ flex:1; }}
.sv {{ font-variant-numeric:tabular-nums; font-weight:600; }}
/* grid, not flex: flex items keep a min-content floor and the last card
   overflowed the printable width instead of shrinking. */
.big {{ display:grid; grid-template-columns:repeat({ncols},minmax(0,1fr)); gap:5mm; margin:0 0 6mm; }}
.kpi {{ border:.5pt solid var(--rule); padding:3mm; }}
.kpi .v {{ font-size:17pt; font-weight:650; font-variant-numeric:tabular-nums;
  line-height:1.1; color:var(--accent); }}
.kpi .l {{ font-size:7.8pt; color:var(--ink-3); margin-top:.8mm; }}
section.tier {{ break-inside:auto; margin:0 0 7mm; }}
section.tier h2 {{ font-size:12.5pt; margin:0 0 1.5mm; padding-bottom:1.5mm;
  border-bottom:1pt solid var(--ink); display:flex; align-items:baseline; gap:2.5mm; }}
.tnum {{ background:var(--accent); color:#fff; font-size:8pt; padding:.6mm 2mm;
  border-radius:1mm; font-weight:600; }}
.tcount {{ margin-left:auto; font-size:8.6pt; color:var(--ink-3); font-weight:400; }}
.blurb {{ color:var(--ink-3); font-size:8.4pt; margin:0 0 3mm; }}
section.tier h3 {{ font-size:9.4pt; margin:4mm 0 1.5mm; color:var(--accent);
  break-after:avoid; }}
.gcount {{ color:var(--ink-3); font-weight:400; font-size:8pt; }}
table {{ width:100%; border-collapse:collapse; margin:0 0 1mm; }}
thead {{ display:table-header-group; }}
th {{ text-align:left; font-size:7.6pt; text-transform:uppercase; letter-spacing:.5pt;
  color:var(--ink-3); font-weight:600; padding:1mm 2mm 1mm 0;
  border-bottom:.5pt solid var(--rule); }}
td {{ padding:1.4mm 2mm 1.4mm 0; border-bottom:.4pt solid var(--rule);
  vertical-align:top; }}
tr {{ break-inside:avoid; }}
.w-name {{ width:24%; }} .w-num {{ width:8%; }} .w-tier {{ width:20%; }}
.w-rel {{ width:12%; }} .w-why {{ width:46%; }}
td.name a {{ color:var(--ink); text-decoration:none; font-weight:600; display:block; }}
td.name .handle {{ display:block; color:var(--ink-3); font-size:7.8pt; }}
/* keep-all stops CJK from breaking mid-term, e.g. 机器人公司决策|者 */
td.tier {{ color:var(--ink-2); font-size:8.2pt; word-break:keep-all; }}
td.num {{ font-variant-numeric:tabular-nums; text-align:right; padding-right:3mm;
  color:var(--ink-2); }}
td.why {{ color:var(--ink-2); }}
.pill {{ font-size:7.6pt; padding:.5mm 1.6mm; border-radius:1mm; white-space:nowrap; }}
.rel-mutual {{ background:#e3efe4; color:#22572a; }}
.rel-in {{ background:#e6eef6; color:#1f4e79; }}
.rel-out {{ background:#f4efe2; color:#6b5518; }}
.rel-none {{ background:#f1f2f4; color:var(--ink-3); }}
.method {{ margin-top:7mm; padding-top:3mm; border-top:.5pt solid var(--rule);
  font-size:8pt; color:var(--ink-3); }}
.method h3 {{ font-size:8.6pt; color:var(--ink-2); margin:0 0 1.5mm; }}
.method li {{ margin-bottom:1.2mm; }}
.method ol {{ padding-left:5mm; margin:0; }}
</style></head><body>

<h1>{html.escape(cfg["title"])}</h1>
<p class="sub">来源:@{html.escape(source)} 的关注列表({_fmt(total_src)} 个账号)&nbsp;·&nbsp;
逐个判定 {_fmt(len(judg))} 个&nbsp;·&nbsp;入选 {_fmt(len(rows))} 人&nbsp;·&nbsp;
本文档正文 {_fmt(len(body_rows))} 人,全量见同名 CSV&nbsp;·&nbsp;数据抓取于 {snap_date}</p>

<div class="brief">
<h2>{html.escape(cfg.get("brief_heading", "筛选依据:这家公司在做什么"))}</h2>
{brief}
</div>

<div class="big">
{kpis}
</div>

<div class="cols"><div class="col">
<h3>按分类分布</h3>
{catlines}
</div><div class="col">
<h3>如何用这份名单</h3>
{howto}
</div></div>

{warm_block}
{section(3, [r for r in body_rows if r["tier"] == 3], "强相关", tier_blurbs.get(3, DEFAULT_TIER_BLURBS[3]))}
{section(2, [r for r in body_rows if r["tier"] == 2], "中相关", tier_blurbs.get(2, DEFAULT_TIER_BLURBS[2]))}

<div class="method">
<h3>方法与口径</h3>
<ol>
<li>名单来自 @{html.escape(source)} 的关注列表,共 {_fmt(total_src)} 个账号,其中
{_fmt(len(judg))} 个有 bio 可判定。未做关键词预筛——bio 写「Professor at MIT」的人
不含任何机器人关键词,但可能属于名单目标,关键词预筛会漏掉。</li>
<li>每个账号由 LLM 按上述公司背景逐一判定 tier、分类与理由,理由必须引用
bio 中的实际信息。回复以 handle 校验,对不上的直接丢弃而非错配。</li>
<li><strong>本 PDF 正文只收录 T{pdf_min_tier} 及以上({_fmt(len(body_rows))} 人)
{"与「优先触达」名单" if warm_block else ""}。</strong>
CSV 是入选全量 {_fmt(len(rows))} 人,一条不少。更低 tier 未导出。</li>
{rel_method}
<li>分类为单选,取此人对这家公司最主要的价值,不代表其全部研究方向,以理由栏为准。
粉丝数为抓取当日快照。</li>
{sources_li}
</ol>
</div>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--self-graph", default=None,
                    help="your own graph json (tools/fetch_graph.py) for the relation column")
    ap.add_argument("--self-name", default=None,
                    help="display name for the relation column, e.g. @YourHandle")
    ap.add_argument("--min-tier", type=int, default=2, help="CSV cutoff")
    ap.add_argument("--pdf-min-tier", type=int, default=3, help="PDF body cutoff")
    a = ap.parse_args()
    if a.self_graph and not a.self_name:
        a.self_name = "@" + json.loads(Path(a.self_graph).read_text()).get("handle", "me")

    camp = Path(a.campaign)
    source, rows, judg, cfg, cat_label, cat_order = load(
        a.infile, camp, a.min_tier, a.self_graph)
    total_src = json.loads(Path(a.infile).read_text())["count"]
    snap_date = dt.date.fromtimestamp(Path(a.infile).stat().st_mtime).isoformat()
    stem = camp / f"shortlist-{source.lower()}"

    write_csv(Path(f"{stem}.csv"), rows, cat_label, a.self_name)
    Path(f"{stem}.html").write_text(build_html(
        source, rows, judg, total_src, a.pdf_min_tier, cfg, cat_label, cat_order,
        a.self_name, snap_date))

    if Path(CHROME).exists():
        subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={stem}.pdf", "--virtual-time-budget=20000",
                        f"file://{Path(stem).resolve()}.html"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print(f"Chrome not found at {CHROME} (set CHROME_BIN); wrote HTML/CSV only")

    print(f"CSV {len(rows)} rows (tier >= {a.min_tier}) | PDF body tier >= {a.pdf_min_tier}")
    for t in (3, 2):
        print(f"  T{t}: {sum(1 for r in rows if r['tier'] == t)}")
    if a.self_name:
        for rel in REL_ORDER:
            print(f"  {rel}: {sum(1 for r in rows if r['relation'] == rel)}")
    for ext in ("pdf", "csv"):
        p = Path(f"{stem}.{ext}")
        if p.exists():
            print(f"  -> {p} ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
