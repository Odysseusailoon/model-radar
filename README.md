# Model Radar 📡 — OSS 前沿模型 GTM 情报雷达

为 **MiniMax GTM 团队**持续追踪 OSS 前沿大模型阵营(MiniMax 自己 + Kimi/Moonshot、
GLM/Z.ai 等竞品)在 X (Twitter) 上的**可引用证据**与**竞争/合作情报**:LLM 自动分类,
沉淀成可筛选、可导出、可推送到飞书(Lark)的结构化情报,并每天监测各实验室官方号的新动态。

> _Track the OSS frontier-model field — demos, customer cases, expert takes, partnerships,
> and eval results — and turn it into citable, filterable, Lark-pushable intelligence for GTM._

### 它解决什么

市场/销售想引用真实社会证据(demo / 客户 case / 大佬评价)时,素材散落在时间线里、难以
检索取用;与此同时,GTM 又需要盯竞品的**合作、集成、企业采用、评测排名**动向。Model Radar
把这两件事收进同一个可运营的后台。

### 核心能力

- **多产品复用是一等公民**:产品名 / 关键词 / 官方号 / 种子 KOL / launch 日期都是数据库
  配置行。加一个新产品 = 在 `/admin/products` 填一张表单,**零代码改动**。
- **七类证据分类(Claude Haiku)**:真实 Demo / 客户 Case / 大佬评价 / **合作集成** /
  资讯 / 推广 / 无关,外加 `竞争情报` 与 `评测/基准` 标记(抓取 SWE-bench、LMArena 等
  榜单提及)。
- **跨产品对比不丢**:一条“M2 吊打 GLM-5 和 Kimi K3”的对比推会同时挂到三个产品下——
  竞争对比正是 GTM 最想要的情报。
- **飞书告警**:高影响力提及 / 合作情报 / 高置信证据三类卡片,去重推送到 Lark。
- **每日实验室监测**:每天拉取各 OSS 实验室官方号的新推 + **关注列表 diff**——实验室新增
  关注某公司/人,常是合作/招聘/兴趣的早期信号 → 飞书卡片。
- **KOL 发现工具**(`tools/build_kol_list.py`):从一组种子实验室/研究者账号的关注交集里
  挖掘高可信度 KOL(被 ≥N 个种子共同关注),按粉丝排序产出候选名单。

### 页面一览

| 路由 | 用途 |
|---|---|
| `/` | **概览**:证据量趋势、分类/情感分布、Top 声量、总 reach |
| `/digest` | **周报**:按产品汇总本周合作/Demo/评测亮点 + 环比 |
| `/feed` | **证据流**:筛选 + 逐条人工复核(通过/拒绝) |
| `/admin/products` | **产品配置**:关键词/官方号/种子 KOL/launch |
| `/export` | 按当前筛选**导出 CSV**(带 BOM,Excel 友好) |
| `/debug/collect` · `/debug/follow-watch` | 手动触发采集 / 每日监测(Basic Auth) |

全站 HTTP Basic Auth(`marketing` / `DASHBOARD_PASSWORD`);单进程部署,uvicorn 同时服务
后台并跑 APScheduler 定时任务。

---

## 目录结构

```
app/
  main.py        FastAPI 应用:dashboard / 复核 / 导出 / admin / webhook / health + APScheduler
  config.py      所有环境变量(密钥、阈值、护栏)—— 产品配置不在这里,在数据库
  db.py          SQLAlchemy engine / session,启动自动建表
  models.py      三张表:products / evidence / alerts_sent
  crud.py        产品配置增删改 + 从 JSON 播种
  xclient.py     ⭐ 唯一与 twitterapi.io 通信的地方;所有字段映射集中于此
  collector.py   采集编排:关键词阶段(增量)+ 全局 KOL 池(按内容归属)+ 限速加固
  follow_watch.py 每日实验室监测:官方号新推 + 关注列表 diff → partnership 告警
  digest.py      周报聚合:按产品汇总本周合作/Demo/评测亮点 + 环比
  pipeline.py    共享管道:去重 → 分类 → 存储(轮询与 webhook 共用)
  classifier.py  Claude Haiku 分类(含完整分类 prompt),严格 JSON、失败重试
  alerts.py      飞书告警卡片 + 去重
  queries.py     证据筛选(feed 与导出共用同一套筛选语义)
  export.py      CSV 生成(纯函数,便于测试)
  templates/     Jinja2:base / feed / admin_products
tests/           pytest:分类 JSON 解析、去重、导出格式(全部 mock 外部调用)
products.example.json   K3 示例 + 空的 GLM 模板
Dockerfile  docker-compose.yml  railway.json  requirements.txt
```

---

## 本地跑起来(Docker,推荐)

前置:装好 Docker Desktop。

1. 复制环境变量模板并填入你的 key:
   ```bash
   cp .env.example .env
   # 编辑 .env:至少填 TWITTERAPI_KEY、ANTHROPIC_API_KEY;想收告警再填 FEISHU_WEBHOOK_URL
   ```
2. 起服务(app + postgres):
   ```bash
   docker compose --env-file .env up --build
   ```
   - 首次启动会自动建表,并从 `products.example.json` 播种一个 **K3** 测试产品配置
     (因为 `SEED_PRODUCTS_FILE=products.example.json`)。
   - ⚠️ 播种只在 products 表为空时发生。之后请用 `/admin/products` 管理产品。
3. 打开 dashboard:<http://localhost:8000/>
   - 账号 `marketing`,密码为你在 `.env` 里设的 `DASHBOARD_PASSWORD`。
4. **不想等 10 分钟?** 立即采集一次(需 Basic Auth):
   ```bash
   curl -u marketing:你的密码 -X POST http://localhost:8000/debug/collect
   ```
   返回本次采集统计。刷新 `/` 即可看到入库并被分类的推文。

> 先去 `/admin/products` 把 K3 的关键词改成能真正命中、且能消歧的词
> (裸 `K3` 会命中一堆汽车/相机噪声)。改完下一个周期(或再点一次 `/debug/collect`)生效。

### 本地跑(不用 Docker)

```bash
pip install -r requirements.txt
# 需要一个可连的 Postgres,并设置 DATABASE_URL 及其它环境变量
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
```

### 跑测试

```bash
pip install -r requirements.txt
pytest
```
3 个测试文件覆盖:分类器 JSON 解析/归一化、去重逻辑、CSV 导出格式。全部 mock 外部调用,
不需要网络或数据库。

---

## 部署到 Railway

1. **建项目**:Railway → New Project → Deploy from GitHub repo(选本仓库)。
   Railway 会识别 `railway.json` 用 Dockerfile 构建。
2. **加 Postgres**:项目里 New → Database → PostgreSQL。Railway 会自动把
   `DATABASE_URL` 注入到 app 服务(无需手填)。
3. **设环境变量**(app 服务 → Variables):
   - `TWITTERAPI_KEY`、`ANTHROPIC_API_KEY`(=你的 aihubmix key)、`ANTHROPIC_BASE_URL`
   - `DASHBOARD_PASSWORD`、`FEISHU_WEBHOOK_URL`、`WEBHOOK_SECRET`
   - 其余可用默认值(见下表)。
   - 想让线上首启也自动播种,再设 `SEED_PRODUCTS_FILE=products.example.json`。
4. **部署**:push 到默认分支即触发。健康检查走 `/health`。
   进程常驻,APScheduler 每 10 分钟在进程内跑一次采集。
5. 部署后同样可 `POST /debug/collect`(带 Basic Auth)立即验证。

> 单服务部署:同一个 uvicorn 进程既服务 dashboard 又跑采集定时任务
> (APScheduler 在 FastAPI lifespan 里启动)。不需要第二个 worker/服务。

---

## 环境变量说明

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `TWITTERAPI_KEY` | ✅ | — | twitterapi.io 的 API key(请求头 `X-API-Key`) |
| `TWITTERAPI_BASE_URL` | | `https://api.twitterapi.io` | 一般不用改 |
| `ANTHROPIC_API_KEY` | ✅ | — | **填你的 aihubmix key**;经 aihubmix 的 Anthropic 兼容端点调用 |
| `ANTHROPIC_BASE_URL` | | `https://aihubmix.com` | aihubmix 的 Anthropic 兼容网关 |
| `CLASSIFIER_MODEL` | | `claude-haiku-4-5-20251001` | 分类模型 |
| `DATABASE_URL` | ✅(线上自动) | localhost | Railway 自动注入;支持 `postgres://` 自动转 `postgresql+psycopg://` |
| `DASHBOARD_USER` | | `marketing` | Dashboard Basic Auth 用户名 |
| `DASHBOARD_PASSWORD` | ✅ | `changeme` | Dashboard Basic Auth 密码,**务必改** |
| `FEISHU_WEBHOOK_URL` | | 空 | 飞书自定义机器人 webhook;留空则不发告警 |
| `WEBHOOK_SECRET` | | 空 | `/webhook/tweets` 的共享密钥(请求头 `X-Webhook-Secret`) |
| `COLLECT_INTERVAL_MINUTES` | | `10` | 采集周期 |
| `MAX_TWEETS_PER_CYCLE` | | `300` | **成本护栏**:单周期最多分类多少条推文 |
| `MAX_PAGES_PER_QUERY` | | `5` | 每个关键词 query 每周期最多翻几页(每页约 20 条) |
| `MAX_SEED_KOLS_PER_CYCLE` | | `15` | 全局 KOL 池每周期最多轮询多少个(轮转覆盖全部,免费档降压) |
| `DIGEST_MIN_FOLLOWERS_EXPERT` | | `10000` | 周报"大佬评价"高亮的粉丝下限 |
| `DIGEST_MIN_FOLLOWERS_CASE` | | `2000` | 周报"客户 Case"高亮的粉丝下限 |
| `DIGEST_MIN_CONFIDENCE` | | `0.6` | 周报高亮的置信度下限 |
| `ALERT_MIN_FOLLOWERS` | | `10000` | high_signal 告警的最低粉丝门槛 |
| `ALERT_MEGA_FOLLOWERS` | | `100000` | mega_mention 告警的粉丝门槛 |
| `ALERT_MIN_CONFIDENCE` | | `0.75` | high_signal / partnership 告警的最低置信度 |
| `FOLLOW_WATCH_ENABLED` | | `true` | 每日实验室监测(官方号新推 + 关注 diff)开关 |
| `FOLLOW_WATCH_HOUR_UTC` | | `1` | 每日监测运行的 UTC 小时(0-23) |
| `FOLLOW_WATCH_MAX_PAGES` | | `20` | 每个被监测账号每次最多翻多少页关注(每页 200) |
| `FOLLOW_WATCH_MIN_TARGET_FOLLOWERS` | | `1000` | 新增关注告警的粉丝门槛(低于则不推,降噪) |
| `SEED_PRODUCTS_FILE` | | 空 | 设为 `products.example.json` 则在表为空时播种 |
| `XCLIENT_DEBUG` | | 空 | 设 `1` 时把每批第一条原始推文打进日志,用于核对字段 |

---

## 成本估算

两块外部成本:

- **twitterapi.io**:按请求/条计费,以其官网价目为准。护栏:`MAX_TWEETS_PER_CYCLE`(默认 300)
  × 每天 144 个周期(10 分钟一次)= 单产品每天最多约 4.3 万条被"处理"。实际远低于此,
  因为增量水位线让每周期只处理**新增**推文。
- **LLM 分类(Claude Haiku)**:每条推文一次调用,输入约 400–700 token、输出约 200 token。
  以 Haiku 量级单价估算,每条约 $0.0003–0.0006。即使护栏打满(300 条/周期),单产品单周期
  约 $0.1–0.2;但稳态下每周期通常只有个位数到几十条新推文,日成本一般在 $1 以内/产品。

**关键防爆点**:`MAX_TWEETS_PER_CYCLE` 是硬上限。如果关键词配得太宽(如裸 `K3`),
命中量会暴涨——护栏会截断在 300 条/周期,并在日志里 `WARN`。看到该告警就去
`/admin/products` 收紧关键词。

---

## "字段对不上怎么办"排障指引 ⭐

twitterapi.io 的返回字段全部集中映射在 **`app/xclient.py`** 一个文件里
(顶部有大号提示 banner)。若某个值一直是空/0/错:

1. 设环境变量 `XCLIENT_DEBUG=1` 重启,采集时会把每批**第一条原始推文 JSON** 打进日志。
2. 对照日志里的真实字段名,改 `xclient.py` 里的:
   - `_map_tweet`(推文字段:id / text / createdAt / *Count 等)
   - `_map_author`(作者字段:userName / followers / description / isBlueVerified)
   - `_extract_media`(**媒体最可能对不上**——见下)
3. 端点路径 / 参数名 / 响应信封键也都在该文件顶部常量里(`ADVANCED_SEARCH_PATH`、
   `KEY_TWEETS` 等),照 <https://docs.twitterapi.io> 最新文档改即可。

**已核对(2026-07-19,依据 docs.twitterapi.io)**:
- Advanced Search:`GET /twitter/tweet/advanced_search`,参数 `query` / `queryType` / `cursor`,
  信封 `{tweets, has_next_page, next_cursor}`
- User Last Tweets:`GET /twitter/user/last_tweets`,参数 `userId|userName` / `cursor` / `includeReplies`
- 认证头:`X-API-Key`
- 推文字段:`id, text, url, createdAt, likeCount, retweetCount, replyCount, quoteCount, viewCount, lang, author, entities`
- 作者字段:`userName, name, followers, description, isBlueVerified`

**⚠️ 未在文档中明确、需按真实响应核对的点**(代码里已用注释标出):
- **媒体字段**:官方 OpenAPI 未文档化 photo/video 如何出现在推文里。`_extract_media`
  目前探测几种常见形态(`extendedEntities.media[].media_url_https`、`entities.media[]`、
  `media[]`)。若 demo 检测缺媒体,用 `XCLIENT_DEBUG=1` dump 一条真实推文再调整。
- **`createdAt` 格式**:假定为 Twitter 经典格式 `"Wed Oct 10 20:19:24 +0000 2018"`,并带
  ISO-8601 兜底。若解析告警,改 `_parse_created_at`。

---

## 系统行为速览

- **采集**(APScheduler,每 `COLLECT_INTERVAL_MINUTES` 分钟),两阶段:
  - **关键词阶段**:对每个 active 产品,用 OR 拼接关键词做 advanced search
    (`-filter:retweets` 排除转推),按 snowflake tweet_id 水位线增量。
  - **KOL 池阶段**:所有产品的 `seed_kols` **合并去重成一个全局池**,每个 KOL 每轮只轮询
    一次(轮转窗口,见下),拿到的每条推按**内容里提到哪个产品**归属——一份 KOL 名单服务
    所有模型,@karpathy 发 GLM 就入库到 GLM 下;对比推同时挂到它提及的每个模型;与所有
    产品无关的 KOL 推**直接跳过、不花 LLM**。
  - **限速加固**(免费档 1 请求/5 秒):`collect_once` 全局互斥锁(手动 `/debug/collect`
    不会和定时任务并发撞限速)+ **产品起始位每轮轮转**(不再永远让最后一个产品被饿死)+
    `MAX_SEED_KOLS_PER_CYCLE` 限量轮转 KOL + **每个数据源失败显式上报**(返回 `sources_failed`
    / `errors`,不再静默吞掉,失败 vs "真没有"分得清)。
- **分类**(Claude Haiku):每条新推文输出严格 JSON(见 `classifier.py` 的完整 prompt)。
  七类互斥 category:`demo / customer_case / expert_review / partnership / news / promo /
  irrelevant`,外加竞争情报标记 `is_competitor_signal`、评测标记 `eval_signal` 与
  `benchmark_names`。**收紧了可信度判据**:蓝V单独不算权威、空泛夸赞不算大佬评价、
  随手一测不算客户 Case。JSON 解析失败重试一次,再失败则以 `classification_failed=True`
  入库,**不丢数据**。
- **存储**(Postgres):`evidence` 去重按 **`(tweet_id, product_id)`** 复合唯一——同一条
  推文可挂到它提及的每个产品(跨产品对比推是核心竞争情报,不能丢);`category/sentiment/
  confidence` 冗余列便于筛选;`review_status` 默认 `pending`。
- **告警**(飞书):三种类型,经 `alerts_sent` 去重 →
  `mega_mention`(粉丝≥10万的相关提及)、
  `partnership_signal`(`partnership` 且 `confidence≥0.75`,**不设粉丝门槛**——合作是事件)、
  `high_signal`(`demo/customer_case/expert_review` 且 `confidence≥0.75` 且粉丝≥1万)。
- **Dashboard**:`/` 概览图表;`/digest` **周报**——按产品汇总本周合作/Demo/评测亮点 + 环比,
  **只露够格的证据**(质量下限:大佬评价需粉丝≥1万、客户 Case 需粉丝≥2千、demo 需有产出物媒体;
  合作/评测不设粉丝门槛;原始分类计数不变、全部数据仍在证据流里);`/feed` 证据流(顶部筛选 +
  每卡 Approve/Reject);`/export` 按当前筛选导出 CSV;`/admin/products` 产品配置表单。
  全站 HTTP Basic Auth。
- **每日实验室监测**(APScheduler `cron`,每天 `FOLLOW_WATCH_HOUR_UTC` 点):对每个 active
  产品的 `official_accounts`(各 OSS 实验室官方号):(a) 直接拉取其**最新推文**过一遍 pipeline
  ——实验室自宣的合作/集成会分类为 `partnership` 并触发飞书卡片;(b) 快照其**关注列表**并与
  昨日对比,**新增关注**→ 推 `🔗 新增关注情报` 卡片(实验室新关注某公司/人,常是合作/招聘/
  兴趣的早期信号)。首日为 baseline(只存不告警);检测与告警分离,飞书失败次日自动重试。
  可 `POST /debug/follow-watch`(Basic Auth)手动触发。存量对比落在 `follow_edges` 表。
- **Webhook**(预留):`POST /webhook/tweets`,校验 `X-Webhook-Secret`,与轮询共用同一 pipeline。

---

## 设计假设(实现时按最合理方式处理,列此备查)

1. **`filter:retweets` 解释为"排除转推"**:转推不是原创社会证据,故用 `-filter:retweets`。
   若你确实想*只要*转推,把 `collector.build_query` 里的 `-filter:retweets` 改掉即可。
2. **增量水位线用 tweet_id(snowflake)而非时间戳**:id 单调、无时钟漂移问题;keyword 搜索
   用 `queryType=Latest`(最新在前),配合水位线跳过已见。
3. **mega_mention 告警要求 `relevant=True` 且非 irrelevant**:避免同名歧义(K3 汽车)的
   10 万粉账号误触发告警。规范里的"无论分类"理解为"不限证据三类",但仍需与产品相关。
4. **aihubmix 作为 Anthropic 兼容网关**:把 `ANTHROPIC_BASE_URL` 指向 aihubmix,
   `ANTHROPIC_API_KEY` 填 aihubmix 的 key,用官方 anthropic SDK 调用。
5. **播种仅在 products 表为空时发生**:避免每次重启覆盖用户在 admin 里的改动。
6. **去重按 `(tweet_id, product_id)` 复合唯一**:同一条推文可同时归属它提及的多个产品——
   跨产品对比推(“M2 吊打 GLM-5 和 Kimi K3”)正是 GTM 最想要的竞争情报,不能只算给先入库的
   那个产品。旧库(全局唯一 `tweet_id`)由 `db._migrate_tweet_dedup` 在启动时就地迁移
   (Postgres:DROP 旧约束 → ADD 复合约束,幂等)。
7. **单进程内 APScheduler**:Railway 单实例常驻。若未来横向扩容多实例,需要把采集任务
   改为单例(如 leader 选举或独立 worker 服务),否则多实例会重复采集。
