# Model Radar

把 X 和公开 OSS 生态证据整理成可复核的模型发布报告、KOL 名单、外联清单与飞书/PDF 交付物。

这个仓库来自真实的模型 GTM 工作流。它更像一个 **script-first intelligence workbench**，
不是一个要求长期部署的 SaaS：先围绕具体问题采集公开证据，再人工或借助 coding agent 复核，
最后产出能回到原帖、能解释口径、能重复运行的报告。

> 仓库只发布代码、模板和不含真人数据的文档。抓取结果、联系人名单、截图、私信、报价与
> 未公开 campaign 信息都留在本地，不进入 git。

## 最近实际在怎么用

| 交付物 | 最近的实际问题 | 从哪里开始 | 典型输出 |
|---|---|---|---|
| 发布复盘报告 | 一个模型 launch 后，声量、好/坏 case、本地部署、渠道接入和 D+10 留存如何变化？ | `tools/m31_flash_launch_*`、`tools/m31_flash_d10_*` | 带原帖链接的 Markdown、JSON、PDF |
| 竞品与舆情扫描 | Kimi、GLM、DeepSeek、GPT、Gemini 等发布时，官方、合作方和用户分别在说什么？ | `tools/release_reaction_scan.py`、`tools/flagship_launch_*`、各主题 `*_scan.py` | 分类证据、对比表、发布节奏时间线 |
| KOL / Core Influencer 名单 | 哪些研究者、开发者和 infra 账号被多个种子共同关注，值得进入长期观察或外联池？ | `tools/build_kol_list.py`、`tools/fetch_graph.py`、`tools/mutuals.py` | 去重名单、关系字段、CSV |
| Campaign 外联名单 | 某位研究者的关注列表里，谁更可能对一个产品、活动或合作方向感兴趣？ | `tools/fetch_followings.py`、`tools/score_relevance.py`、`tools/build_outreach_report.py` | 分层 PDF + 飞书可导入 CSV |
| OSS 生态追踪 | 新增了哪些权重、量化、推理后端、工作流或社区集成？哪些只是研究结果，哪些已有可用 artifact？ | `app/h3_watch.py`、公开 repo/模型页证据、`tools/readme_to_feishu.py` | 生态更新清单、README patch、飞书审阅稿 |
| 周报与证据库 | 需要持续监测多个模型，而不是只做一次报告 | `app/` | Dashboard、证据流、周报、CSV、飞书告警 |

高频路径其实是前三种：**围绕一个明确问题写查询 → 拉公开证据 → 复核 → 聚合 → 交付**。
常驻 Dashboard 是可选能力，不是使用这个仓库的前提。

## 工作流

```text
公开问题
  ↓
查询窗口与口径（写进脚本）
  ↓
X / GitHub / Hugging Face 等公开证据
  ↓
去重、分类、人工复核
  ↓
数字 + 可点击证据 + 限制说明
  ↓
Markdown / CSV / PDF / 飞书
```

每轮工作都遵守四条规则：

1. **先定义口径，再跑数字。** 时间窗、query 形状、分页上限和排除规则必须能回读。
2. **每个重要判断都能点回原证据。** 推文 ID、repo、模型页和发布日期不靠记忆补。
3. **区分公开事实、分析判断和未验证线索。** 集成不等于合作；draft 不等于发布；研究结果不等于可用权重。
4. **真人数据不进仓库。** 代码可复用，抓取 payload、联系人清单和沟通内容不可默认公开。

## Quick start

### 1. 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

大多数 live X 扫描只需要在 `.env` 中填写：

```dotenv
TWITTERAPI_KEY=your_key
```

如果你已经有缓存 JSON，做聚合、审阅、转 CSV 或渲染报告时不需要任何外部 API key。

### 2. 先跑一个真实的发布复盘

下面这组脚本保留了 M3.1 Flash launch 与 D+10 复盘的真实查询结构：

```bash
# 按主题和时间窗抓公开 X 证据
TWITTERAPI_MIN_INTERVAL=1.2 \
  .venv/bin/python tools/m31_flash_d10_scan_20261029.py --group main --suffix -local

# 拉同口径日声量，避免只看一个孤立数字
TWITTERAPI_MIN_INTERVAL=1.8 \
  .venv/bin/python tools/m31_flash_d10_volume_20261029.py

# 先列出这一组会跑哪些 query，不发请求
.venv/bin/python tools/m31_flash_d10_scan_20261029.py --group main --list
```

日期脚本是 run record，不是抽象 SDK。复制一组最接近的脚本，修改窗口、关键词、对照组和
输出目录，通常比从零写一个“万能扫描器”更可审计。`*_analyze_*.py` 需要对应目录中已有
分类结果；只有 raw scan 时，先人工或用下一节任一方式生成该脚本约定的 `classified.json`。

### 3. LLM 分类是可选步骤

采集和渲染不依赖 LLM。需要批量分类时有三种方式：

- 直接让 Claude Code、Codex 或其他 coding agent 读取缓存 JSON，按项目 schema 输出分类结果；
- 使用你自己的模型/API，把结果写成分析脚本期望的 JSON；
- 运行仓库里的 `*_classify_*.py` 或 `tools/score_relevance.py`。这些脚本使用
  Anthropic-compatible 环境变量，只有走这条路径时才需要相应的 LLM credential。

因此，**这个仓库没有第二把“必填模型 API key”**。最近几轮实际工作主要是 live X 采集加
agent-assisted review；不要为了跑扫描先配置一个不需要的 LLM 网关。

## Use case 1：模型发布复盘

适合回答：

- launch 当天到底出现了哪些真实使用 case，而不是只有转发和宣传？
- open weights 发布后，GGUF、MLX、vLLM、SGLang、Ollama 等生态接入何时出现？
- 用户是在继续使用、开始付费，还是几天后切回其他模型？
- 与竞品相比，声量、渠道覆盖和有效证据密度如何？

一轮标准目录：

```text
reports/<date>-<topic>/
  evidence/          原始抓取与分片结果
  *.log              query、窗口、分页和错误
  analysis.json      结构化分类与聚合
  REPORT.zh-CN.md    正文
  _feishu-*.md       飞书导入版
```

典型步骤：

```bash
# 1. scan：按小时/主题拆 query，避免超长 query 和分页截断
.venv/bin/python tools/m31_flash_launch_scan_20261019.py

# 2. classify：可选；脚本支持缓存或断点续跑
.venv/bin/python tools/m31_flash_launch_classify_20261019.py

# 3. analyze：聚合类别、渠道、竞品、好坏 case 与引用
.venv/bin/python tools/m31_flash_launch_analyze_20261019.py

# 4. render：Markdown → A4 PDF
node tools/md_to_pdf.mjs REPORT.zh-CN.md out.html out.pdf "MODEL RADAR"
```

仓库里还有 release reaction、flagship launch、Space Bunny、GLM、GPT、Gemini、Muse、
Forkscope 等公开主题脚本。它们的价值是保留当时的查询设计和分析 schema，不代表对应报告
或原始数据已经公开。

## Use case 2：KOL 与外联名单

### 种子关注交集 → KOL 候选

`build_kol_list.py` 会优先复用已有缓存，只对缺失种子做 live fetch：

```bash
TWITTERAPI_KEY=your_key .venv/bin/python tools/build_kol_list.py
```

适合找“被多个实验室、研究者或 infra 账号共同关注的人”。交集强度只是发现信号，不能自动
等同于影响力、合作意向或 endorsement；进入名单前仍要看个人资料和近期内容。

### 关注列表 → campaign 名单

```bash
# 0. 从模板建立一个本地 campaign
cp -r campaigns/templates/customer-discovery campaigns/my-campaign
# 编辑 scoring-prompt.md 和 config.json，替换所有【填空】

# 1. 抓源账号关注列表
.venv/bin/python tools/fetch_followings.py some_researcher

# 2. 可选：批量打分；也可以由 coding agent 或自有模型生成同 schema 结果
.venv/bin/python tools/score_relevance.py some_researcher-followings.json \
  --campaign campaigns/my-campaign

# 3. 加自己的关系图并输出 PDF + CSV
.venv/bin/python tools/fetch_graph.py YourHandle
.venv/bin/python tools/build_outreach_report.py some_researcher-followings.json \
  --campaign campaigns/my-campaign \
  --self-graph yourhandle-graph.json \
  --self-name @YourHandle
```

四套起始模板在 `campaigns/templates/`：customer discovery、KOL launch、investor scan、
talent scan。模板可以公开；真实 campaign 目录、评分结果和联系人资料默认 gitignore。

## Use case 3：OSS 生态追踪

这条线不只看“谁发了推”，而是持续核对可用 artifact：

- 模型与权重页；
- quantization / GGUF / MLX；
- vLLM、SGLang、Ollama、LM Studio 等推理路径；
- text encoder、VAE、workflow、demo 与复现项目；
- 研究论文、性能声明与实际可下载内容之间的差异。

`app/h3_watch.py` 提供 H3 生态窗口监测；`tools/readme_to_feishu.py` 保留了把 H3 官方生态
README 转成飞书审阅稿时使用的专用规则。它固定读取工作区中的
`MINIMAX-H3-OFFICIAL-README.md`，适合作为新转换器的起点，不是任意 README 的通用 CLI。
维护生态 index 时，先验证链接、license、artifact 状态和归属，再改 README；不要把
“提到模型”升级成“官方合作”。

## Use case 4：交付到飞书和 PDF

```bash
# 普通报告转飞书安全 Markdown
.venv/bin/python tools/feishu_md_escape.py REPORT.zh-CN.md _feishu-REPORT.md

# H3 生态 README 专用转换器；固定读取 MINIMAX-H3-OFFICIAL-README.md
.venv/bin/python tools/readme_to_feishu.py

# Markdown 转打印版 HTML + PDF（首次先 npm install marked）
npm install marked
node tools/md_to_pdf.mjs REPORT.zh-CN.md out.html out.pdf "MODEL RADAR"
```

飞书文档、表格和 PDF 是不同交付物：PDF 适合固定版式审阅，CSV/XLSX 才适合导入多维表格。
“生成了文件”也不等于已经推送、分享或发布，外部终态要单独验证。

## 可选：常驻 Dashboard

`app/` 是 FastAPI + Postgres 的持续监测版本，适合多产品长期运行：

- `/`：概览；
- `/digest`：周报；
- `/feed`：证据流与人工 approve/reject；
- `/admin/products`：关键词、官方账号、种子 KOL 与 launch 日期；
- `/export`：按筛选导出 CSV；
- `/debug/collect`、`/debug/follow-watch`：手动触发采集和每日监测。

Docker 启动：

```bash
docker compose --env-file .env up --build
```

首次可用 `products.example.json` 播种测试产品。Dashboard 自动分类需要配置一个兼容的
LLM endpoint；如果你的目标只是一次发布复盘或名单生成，不必先部署这套服务。

## Repository map

```text
app/                 可选的 FastAPI/Postgres 持续监测服务
  xclient.py         twitterapi.io 的唯一字段映射层
  collector.py       关键词 + 全局 KOL 池采集
  classifier.py      可选的自动分类
  follow_watch.py    官方账号新帖与关注列表 diff
  h3_watch.py        H3 生态窗口监测
  digest.py          周报聚合
  templates/         Dashboard 页面

tools/               高频工作区
  *_scan*.py         采集公开证据
  *_classify*.py     可选批量分类
  *_analyze*.py      聚合与报告数据
  fetch_followings.py / fetch_graph.py / mutuals.py
  build_kol_list.py / score_relevance.py / build_outreach_report.py
  feishu_md_escape.py / readme_to_feishu.py / md_to_pdf.mjs

campaigns/           外联模板与虚构示例；真实 campaign 默认不公开
tests/               外部调用均 mock 的单元与 smoke tests
docs/                辅助文档
products.example.json
```

## 数据与凭证边界

公开仓库包含：

- 通用采集、分类、聚合、渲染代码；
- 只基于公开事实的 dated run scripts；
- 虚构 campaign 示例与空模板；
- 测试和产品配置示例。

默认不公开：

- `reports/`、`outputs/`、`sites/`、`out-h3*/`；
- 根目录生成的 JSON、CSV、HTML、PDF、PNG；
- 真实 campaign 工作区；
- 主页截图、逐字推文 payload、联系人清单；
- 私信、报价、未发布产品定位与内部飞书 token；
- `.env` 与 `.lark-auth/`。

判断标准不是“代码还是数据”，而是文件里有没有别人的内容、未公开计划或可用 credential。
有，就不提交。即使数据来自公开 X，批量人物画像和逐字 payload 也不应默认进入公开 git 历史。

## 采集与分析注意事项

- twitterapi.io 的长 query 可能返回 400；复杂 OR 组要拆成短 query。
- Latest 分页有上限，宽时间窗按小时或主题切分，并在日志中记录缺口。
- 同一条跨模型对比推应挂到所有相关产品，不能只算给第一个命中的模型。
- 声量结论必须带同口径基线；孤立的“抓到 N 条”没有比较意义。
- 先回表核对 tweet ID，再写引用、数字和代表性 case。
- 分类脚本要可续跑；已处理 ID 落盘，失败与“没有结果”分开记录。
- `app/xclient.py` 集中处理 API 字段映射。字段变空时先设 `XCLIENT_DEBUG=1` 看真实响应，
  不要在多个脚本里各写一套猜测。

## Tests

```bash
.venv/bin/pytest
```

测试覆盖分类 JSON 解析、去重、导出、Dashboard、follow watch、H3 watch、bot 与响应信封映射；
外部请求均 mock，不需要 live API key 或数据库。
