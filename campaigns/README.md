# campaigns/ — 关注列表 → 外联名单 pipeline

从任意一个人的 X 关注列表出发,产出一份「谁会对某家公司/产品感兴趣」的
可执行外联名单(PDF + 可导入飞书多维表格的 CSV)。

一个 campaign = 一个目录,放三样东西:

```
campaigns/<name>/
  scoring-prompt.md   打分 system prompt:公司背景 + tier 判据 + 分类 key(你来写)
  config.json         报告配置:标题 / 公司简介段落 / 分类 key→中文标签(与 prompt 保持一致)
  judgments.json      打分缓存(自动生成,增量续跑,换源列表可复用)
  shortlist-*.{csv,html,pdf}   产出(自动生成)
```

`campaigns/example/` 是一个完整的虚构示例,复制一份改内容即可:

```bash
cp -r campaigns/example campaigns/mycompany
# 编辑 campaigns/mycompany/scoring-prompt.md 和 config.json
```

## 四步跑通

```bash
# 1. 抓源账号的关注列表(挑一个「关注了整个圈子」的人,例如领域内知名研究员)
.venv/bin/python tools/fetch_followings.py chris_j_paxton

# 2. (可选)抓你自己的关注/粉丝图谱,用于「与我关系」列
.venv/bin/python tools/fetch_graph.py YourHandle

# 3. LLM 逐个打分(有缓存,断了重跑不重复花钱)
.venv/bin/python tools/score_relevance.py chris_j_paxton-followings.json \
    --campaign campaigns/mycompany

# 4. 出报告:PDF(给人看)+ CSV(导飞书)
.venv/bin/python tools/build_outreach_report.py chris_j_paxton-followings.json \
    --campaign campaigns/mycompany \
    --self-graph yourhandle-graph.json --self-name @YourHandle
```

飞书多维表格只能导入 CSV/XLSX,不能导入 PDF——所以两个都出:
CSV 带 BOM,飞书/Excel 直接识别中文表头;PDF 适合发人、打印、当附件。

## 写 scoring-prompt.md 的要点

- **公司背景先做事实核查**。只写有来源(融资公告、官网、可信报道)的说法,
  并在 config.json 的 `sources_note` 里写明来源——名单会被拿去做真实外联,
  一句没根据的话会跟着每一次转发扩散。
- tier 判据写成**可判定的条件**(做什么方向 / 什么身份),不要写「知名」「有影响力」
  这类模型无法从 bio 验证的形容词。
- 分类 key 必须与 config.json 的 `categories[].key` 一一对应,顺序即报告中的
  优先级顺序。
- prompt 要求模型:理由必须引用 bio 里的实际信息、拿不准给低 tier、只输出 JSON。
  example 里这三条都有,别删。

## 成本参考

- twitterapi.io:关注列表 200 人/页;免费档 1 请求/5 秒,3,700 人的列表约 2 分钟
  (付费档)/ 20 分钟(免费档)。粉丝列表同理。
- LLM 打分:15 人/批,每批约 1 次 Haiku 调用。3,573 人 ≈ 239 批,约 $1–2
  (经 aihubmix 网关,含 thinking 开销)。缓存按 handle 增量,换一个源账号只为
  新面孔付费。
