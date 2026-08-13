# GTM 傻瓜教程 — 不会写代码也能跑

这份教程写给**完全不写代码的 GTM 同学**。你只需要会:打开终端、复制粘贴命令、
按回车。每一步都告诉你「贴什么」和「看到什么算成功」。

工程同学请直接看 [README.md](../README.md)。

---

## 第 0 步:你需要的两把钥匙(10 分钟)

整个仓库只依赖两个付费服务,都是注册即用,不需要公司审批的企业账号:

1. **twitterapi.io**(抓 X/Twitter 数据)
   - 打开 <https://twitterapi.io> → 注册 → Dashboard 里复制 API Key。
   - 免费档能用(限速 1 请求/5 秒),充 $5 就快很多。
2. **aihubmix**(调用 Claude 做判断,不需要海外信用卡)
   - 打开 <https://aihubmix.com> → 注册 → 充值(¥10 起)→ 生成 API Key(`sk-` 开头)。

> 两个 key 都是钱,**别发到群里、别截图**。只放在下面第 2 步的 `.env` 文件里。

---

## 第 1 步:装环境(一次性,15 分钟)

打开「终端」(Mac:聚焦搜索输 Terminal),逐行粘贴,每行按回车等它跑完:

```bash
# 1. 下载仓库(装了 git 的话;没装会自动提示你装)
git clone https://github.com/Odysseusailoon/model-radar.git
cd model-radar

# 2. 建 Python 环境并装依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**看到什么算成功**:最后一行出现 `Successfully installed ...` 一长串,没有红色 ERROR。

---

## 第 2 步:填钥匙(2 分钟)

```bash
cp .env.example .env
open -e .env
```

会弹出一个文本编辑器,只改两行,其他都不用动:

```
TWITTERAPI_KEY=这里粘贴你的 twitterapi.io key
ANTHROPIC_API_KEY=这里粘贴你的 aihubmix key(sk-开头)
```

保存,关掉。完成。

---

## 场景 A:出一份外联名单(最常用)⭐

**你想回答的问题**:「某某大 V 的关注列表里,谁会对我们公司/产品感兴趣?」

**产出**:一份排好版的 PDF(直接发人)+ 一份 CSV(导入飞书多维表格,见场景 C)。
每人带:链接、粉丝数、相关度分层、一句话理由。

### A1. 挑一个"源账号"

选一个**关注了整个目标圈子**的人——通常是这个领域的知名研究员/创始人/KOL。
判断标准:打开他的 X 主页看 Following 数,1,000–5,000 且都是圈内人最理想。

### A2. 建你的 campaign(核心工作,值得花 30 分钟)

从四套模版里挑最接近的(见 `campaigns/templates/README.md`):

| 你想干什么 | 用哪套 |
|---|---|
| 找潜在客户/早期用户 | `customer-discovery` |
| 产品发布找 KOL | `kol-launch` |
| 找投资人 | `investor-scan` |
| 招聘 mapping | `talent-scan` |

```bash
cp -r campaigns/templates/customer-discovery campaigns/my-campaign
open -e campaigns/my-campaign/scoring-prompt.md
open -e campaigns/my-campaign/config.json
```

把所有 **【填空】** 换成你的真实信息。两条红线:

- **只写核实过的公司事实**,来源写进 `config.json` 的 `sources_note`。
  这份名单会被拿去真实外联,写错一句会跟着每次转发扩散。
- tier 判据写成**看 bio 能判断的条件**(做什么方向/什么职位),
  不写「知名」「有影响力」这种模型没法验证的词。

### A3. 跑三条命令

```bash
# ① 抓源账号的关注列表(几分钟,免费档更久)
.venv/bin/python tools/fetch_followings.py 源账号handle

# ② LLM 逐个打分(3,500 人约 $1–2、跑 20-40 分钟;中断了重跑同一条命令,已判过的不重复花钱)
.venv/bin/python tools/score_relevance.py 源账号handle-followings.json --campaign campaigns/my-campaign

# ③ 出报告
.venv/bin/python tools/build_outreach_report.py 源账号handle-followings.json --campaign campaigns/my-campaign
```

**看到什么算成功**:第③步最后打印 `-> campaigns/my-campaign/shortlist-xxx.pdf (xxx KB)`。
PDF 和 CSV 都在 `campaigns/my-campaign/` 里。

### A4.(可选)加「与我关系」列

如果外联要用某个自己人的账号发 DM,可以给名单加一列:每个人和这个账号是
互粉 / 对方已关注 / 已关注未回 / 无关系——报告最前面还会多一页「优先触达」,
列出所有已有关系、可以直接私信的人。

```bash
.venv/bin/python tools/fetch_graph.py 你的handle
.venv/bin/python tools/build_outreach_report.py 源账号handle-followings.json \
    --campaign campaigns/my-campaign --self-graph 你的handle-graph.json --self-name @你的handle
```

### A5. 抽查(别跳过)

发出去之前,打开 PDF 抽查 10 个人:点链接进主页,看理由和本人对不对得上。
LLM 只看 bio,bio 过时或含糊的人会判错。抽查发现某人明显错了,打开
`campaigns/my-campaign/judgments.json`,搜他的 handle 删掉那条,重跑 ②③ 就会重判他。

---

## 场景 B:持续监控产品声量(radar 主体)

**你想回答的问题**:「谁在 X 上聊我们的产品/竞品?有哪些能引用的好评、
值得跟进的合作信号?」

这是仓库的主体功能,带网页后台,适合长期挂着。需要装 Docker Desktop
(工程同学 10 分钟能帮你搞定),之后:

```bash
docker compose --env-file .env up --build
```

打开 <http://localhost:8000>(账号 `marketing`,密码是 `.env` 里的
`DASHBOARD_PASSWORD`),在 `/admin/products` 里配置产品关键词,系统每 10 分钟
自动抓取 + 分类。详细说明看 [README.md](../README.md) 的「本地跑起来」章节。

---

## 场景 C:把 CSV 导入飞书多维表格(点按教程)

> 飞书多维表格**只认 CSV/XLSX,不认 PDF**——所以场景 A 两个都给你。

1. 打开飞书 → 云文档 → 新建 → **多维表格**。
2. 表格里:左上角 **+ 新增** 旁的 ⌄ → **导入数据** → **本地文件**。
3. 选 `campaigns/my-campaign/` 里的 `shortlist-xxx.csv` → 导入。
4. 中文表头、链接列会自动识别(CSV 带了 BOM,不会乱码)。
5. 建议导入后:「相关度」列设筛选、「与 xx 关系」列按「互粉」筛出来先发。

---

## 场景 D:挖一份 KOL 候选名单

**你想回答的问题**:「这个领域可信的 KOL 都有谁?」

思路:选 4-8 个圈内公认的种子账号(实验室官号、知名研究员),被**多个**种子
同时关注的人,大概率是圈内可信声音:

```bash
# 编辑 tools/build_kol_list.py 顶部的 SEEDS 列表,换成你的种子账号
open -e tools/build_kol_list.py
.venv/bin/python tools/build_kol_list.py
```

产出 `kol-candidates-*.json`,按「被几个种子关注」排序。

---

## 常见报错对照表

| 你看到 | 原因 | 办法 |
|---|---|---|
| `TWITTERAPI_KEY not set` | 第 2 步没填 key,或没保存 | 重做第 2 步 |
| `command not found: python3` | 没装 Python | Mac 会自动弹窗提示装,点安装后重试 |
| 打分跑一半断了 | 网络/限速 | **直接重跑同一条命令**,缓存会接着跑,不重复花钱 |
| `batch failed: ...` 偶尔出现几次 | 个别批次解析失败 | 正常,重跑一次命令会补上缺的人 |
| `429` / rate limit | twitterapi.io 免费档限速 | 等几分钟重跑,或充 $5 提速 |
| CSV 导入飞书乱码 | 没用仓库出的 CSV(自己转存过) | 用原始 CSV 重新导入 |
| 报告里某人明显判错 | bio 过时/含糊 | 见 A5:删 judgments.json 里那条,重跑 |

## 成本速查

| 动作 | 花费 |
|---|---|
| 抓 3,700 人关注列表 | twitterapi.io 按请求计费,约 19 页请求;免费档也能跑(慢) |
| LLM 打分 3,500 人 | 约 $1–2(aihubmix 余额) |
| 出 PDF/CSV 报告 | 免费(本地生成) |
| 声量监控挂一天 | 通常 <$1/产品(见 README「成本估算」) |

---

## 安全须知(必读)

- **名单里是几千个真实的人**。抓下来的 JSON、判定结果、PDF/CSV 都默认不进 git
  (已配置好),**也不要**手动上传到公开的地方。内部流转用飞书。
- 两个 API key 等于钱包,只存在 `.env`(已配置为不进 git)。
- 外联文案是另一回事:名单只告诉你**找谁、为什么**,发什么内容请走你团队的
  文案审核流程,尤其不要转述任何未官宣的产品信息。
