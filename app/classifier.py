"""LLM classifier (Anthropic Haiku via the aihubmix Anthropic-compatible gateway).

Each tweet -> strict JSON verdict. Parse failures are retried once; a second
failure is stored (classification_failed=True) rather than dropped.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from .config import get_settings
from .models import Product
from .xclient import Tweet

log = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "demo", "customer_case", "expert_review", "partnership",
    "news", "promo", "irrelevant",
}

SYSTEM_PROMPT = """\
你是一名严谨的 GTM(Go-To-Market)与竞争情报分析员。目标产品既可能是"我方产品",
也可能是"竞品"。你的任务有两层:(1) 判断这条推文能否作为该产品的"可引用社会证据"
(供市场/销售放进 deck / 官推转发 / 销售话术);(2) 判断它是否是值得 GTM 跟进的
"竞争/市场情报"(合作、集成、企业采用、融资、定价、基准评测等),即使它并不适合我方直接引用。

你只输出一个 JSON 对象,不要输出任何解释、前后缀或 markdown 代码块。

分类判据(category,七选一,互斥):
- "demo":用户实际用该产品**做出了东西**,并展示了**产出物**——即"用该产品生成 / 构建出来的
  结果":生成的视频 / 图像 / 网页 / 可运行代码或其输出 / 可访问的 demo 链接 / 具体产物截图。
  ⚠️ **表情包 / 梗图 / reaction 图 / GIF / 纯吐槽配图 / 无关配图 / 只是一张产品 logo 或截图对话
  都不算产出物**——这类即使带图也 **不是 demo**(归 news 或 irrelevant),且 has_media_evidence
  必须为 false。纯说"很好用""太强了"而无产出物 → 也不是 demo。
- "customer_case":某公司 / 团队 / 专业个人描述在**真实业务、生产环境或长期工作流**里使用了
  该产品(例:"我们把它接入了客服系统""用它替换了原来的 X")。关键是真实落地场景。
  ⚠️ 随手拿它测一道题、"我正在拿它跑我手头的难题"这类一次性把玩 **不算** customer_case
  (这类顶多是 demo 或 news)。
- "expert_review":**可信的人**对产品做出**有实质内容**的评价(正负皆可)。两条都要满足,缺一不可:
  (1) 作者具备真实可信度——较高粉丝量(经验阈值:约 1 万以上)**或** bio 明确显示研究员 /
      知名开发者 / 投资人 / 资深从业者。**光有蓝V认证不算**——蓝V是付费即得,不构成权威;
  (2) 评价有实质——涉及能力 / 对比 / 局限 / 基准等具体内容。
  ⚠️ 一句空泛夸赞(如"太强了""increíble""也很不错")即便来自蓝V,也 **不是** expert_review;
  若作者没有实质可信度信号,这类归 news 或 irrelevant,不要硬塞进 expert_review。
- "partnership":宣布或提及该产品的合作 / 集成 / 平台上架 / 企业采用 / 融资 / 重大商业动作
  (例:"X 已上架 AWS Bedrock""某公司与 Moonshot 达成合作""GLM 被集成进 Cursor"
  "Z.ai 完成新一轮融资")。这是核心竞争情报信号,无论出自官方还是第三方都要标为 partnership
  (若同时明显是官方自宣,仍归 partnership,而非 promo——合作事实本身比"谁发的"更重要)。
- "news":关于该产品的资讯 / 发布 / 报道 / 转述,作者本人并未使用或评价,且不含具体合作动作。
- "promo":官方账号自己发布的纯营销 / 抽奖引流 / 无实质信息的推广。若作者handle在官方账号
  列表中且内容无实质情报,倾向判为 promo。
- "irrelevant":与该产品无关,或"K3"等关键词命中了同名的其他事物(车、相机等)。

其他字段判据:
- relevant:该推文是否真的在讲这个目标产品(true/false)。同名歧义命中 → false + irrelevant。
- confidence:0.0-1.0,你对本次分类整体判断的置信度。
- sentiment:positive / neutral / negative。负面同样要如实标注,负面评价对内部竞争分析有价值。
- has_media_evidence:推文是否带有**产出物级别**的媒体/链接/代码证据(true/false)。
  仅当媒体是"用该产品做出来的结果"才为 true;表情包/梗图/reaction/无关配图 → false。
- is_competitor_signal:该推文是否是值得 GTM 主动跟进的竞争/市场情报(true/false)。凡涉及
  合作/集成/企业采用/融资/定价变动/平台上架/重要基准评测结果的,无论正负、无论我方或竞品,
  都为 true。纯粹的个人把玩、空泛夸赞、无关内容为 false。
- eval_signal:该推文是否给出了该产品的具体基准/评测结果、排名或分数(true/false)。
  例:"M2 在 SWE-bench Verified 上 70%""LMArena 排名第二""Artificial Analysis 指数上升"。
- benchmark_names:字符串数组,列出推文中提到的基准/榜单名称(如 "SWE-bench Verified"、
  "LMArena"、"Aider polyglot"、"GPQA")。没有则空数组。
- author_credibility_signals:字符串数组,列出作者可信度线索(如 "前 OpenAI 研究员"、
  "10万粉技术博主"、"蓝V认证")。没有则空数组。
- quotable_excerpt:推文中最适合被引用的一句(保持原文语言,不要翻译)。若无则空字符串。
- summary_zh:一句话中文摘要。
- usable_for_marketing:该条是否适合"我方市场"直接引用(true/false)。仅当讲的是我方产品、
  且是 demo/customer_case/正面且有实质的 expert_review 时通常为 true;竞品内容、promo、
  irrelevant、空泛内容、负面评价通常为 false(负面/竞品仍要入库,作内部竞争参考)。
- usability_reason:一句话说明为什么适合 / 不适合我方市场引用。

输出的 JSON 必须且只能包含这些键:
relevant, category, confidence, sentiment, has_media_evidence,
is_competitor_signal, eval_signal, benchmark_names,
author_credibility_signals, quotable_excerpt, summary_zh,
usable_for_marketing, usability_reason
"""


@dataclass
class ClassificationResult:
    data: dict
    failed: bool


def _default_failed(reason: str) -> dict:
    return {
        "relevant": False,
        "category": "irrelevant",
        "confidence": 0.0,
        "sentiment": "neutral",
        "has_media_evidence": False,
        "is_competitor_signal": False,
        "eval_signal": False,
        "benchmark_names": [],
        "author_credibility_signals": [],
        "quotable_excerpt": "",
        "summary_zh": "",
        "usable_for_marketing": False,
        "usability_reason": "",
        "classification_failed": True,
        "failure_reason": reason,
    }


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction: strip code fences, grab the first {...} block."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("no JSON object found", text, 0)


def _normalize(data: dict) -> dict:
    """Coerce/validate model output into our canonical shape."""
    cat = str(data.get("category", "irrelevant")).strip().lower()
    if cat not in VALID_CATEGORIES:
        cat = "irrelevant"
    sent = str(data.get("sentiment", "neutral")).strip().lower()
    if sent not in {"positive", "neutral", "negative"}:
        sent = "neutral"
    signals = data.get("author_credibility_signals") or []
    if not isinstance(signals, list):
        signals = [str(signals)]
    benchmarks = data.get("benchmark_names") or []
    if not isinstance(benchmarks, list):
        benchmarks = [str(benchmarks)]
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "relevant": bool(data.get("relevant", False)),
        "category": cat,
        "confidence": conf,
        "sentiment": sent,
        "has_media_evidence": bool(data.get("has_media_evidence", False)),
        "is_competitor_signal": bool(data.get("is_competitor_signal", False)),
        "eval_signal": bool(data.get("eval_signal", False)),
        "benchmark_names": [str(b) for b in benchmarks],
        "author_credibility_signals": [str(s) for s in signals],
        "quotable_excerpt": str(data.get("quotable_excerpt", "") or ""),
        "summary_zh": str(data.get("summary_zh", "") or ""),
        "usable_for_marketing": bool(data.get("usable_for_marketing", False)),
        "usability_reason": str(data.get("usability_reason", "") or ""),
        "classification_failed": False,
    }


def _build_user_prompt(tweet: Tweet, product: Product) -> str:
    official = ", ".join(product.official_accounts or []) or "(未提供)"
    media = f"{len(tweet.media_urls)} 个媒体附件" if tweet.media_urls else "无媒体附件"
    return (
        f"目标产品名称:{product.name}\n"
        f"该产品的官方账号(用于判断 promo):{official}\n"
        f"--- 待分类推文 ---\n"
        f"作者 handle:@{tweet.author.handle}\n"
        f"作者昵称:{tweet.author.name}\n"
        f"作者粉丝数:{tweet.author.followers}\n"
        f"作者 bio:{tweet.author.bio or '(无)'}\n"
        f"蓝V认证:{'是' if tweet.author.verified else '否'}\n"
        f"媒体证据:{media}\n"
        f"互动:❤{tweet.like_count} 🔁{tweet.retweet_count} 💬{tweet.reply_count}\n"
        f"推文正文:\n{tweet.text}\n"
        f"--- 请输出 JSON ---"
    )


class Classifier:
    def __init__(self):
        import anthropic  # lazy: keeps pure parse helpers importable without the SDK

        settings = get_settings()
        self.model = settings.classifier_model
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=30.0,
            max_retries=2,  # SDK-level retry for transport/5xx errors
        )

    def _call(self, tweet: Tweet, product: Product) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(tweet, product)}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", None) == "text")

    def classify(self, tweet: Tweet, product: Product) -> ClassificationResult:
        """Classify one tweet. Retries once on JSON-parse failure; a second
        failure returns a failed-marker result (data is still stored upstream)."""
        last_err = ""
        for attempt in (1, 2):
            try:
                raw = self._call(tweet, product)
                data = _normalize(_extract_json(raw))
                return ClassificationResult(data=data, failed=False)
            except (json.JSONDecodeError, ValueError) as exc:
                last_err = f"parse error: {exc}"
                log.warning("Classify parse fail (attempt %d) tweet %s: %s", attempt, tweet.id, exc)
            except Exception as exc:  # network/API errors after SDK retries
                last_err = f"api error: {exc}"
                log.error("Classify API fail (attempt %d) tweet %s: %s", attempt, tweet.id, exc)
        log.error("Classification failed for tweet %s after retry: %s", tweet.id, last_err)
        return ClassificationResult(data=_default_failed(last_err), failed=True)
