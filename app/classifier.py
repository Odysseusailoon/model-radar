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

VALID_CATEGORIES = {"demo", "customer_case", "expert_review", "news", "promo", "irrelevant"}

SYSTEM_PROMPT = """\
你是一名严谨的 GTM(Go-To-Market)证据分析员。你的唯一任务是判断一条推文能否作为
某个 AI 产品的"可引用社会证据",供市场和销售团队放进 deck / 官推转发 / 销售话术。

你只输出一个 JSON 对象,不要输出任何解释、前后缀或 markdown 代码块。

分类判据(category,六选一,互斥):
- "demo":用户实际用该产品做出了东西,并展示了产出物(视频/截图/代码块/可访问链接/
  具体输出)。关键:必须有产出物证据。纯粹说"很好用""太强了"没有产出物 → 不是 demo。
- "customer_case":某公司或个人描述在真实业务 / 工作流 / 生产环境里使用了该产品
  (例:"我们把它接入了客服系统""用它替换了原来的 X")。强调真实使用场景,而非一次性把玩。
- "expert_review":有可信度的人对产品做出有实质内容的评价(正面或负面均可)。要求两点:
  (1) 作者具备可信度信号——粉丝量较高、bio 显示研究员/知名开发者/投资人/资深从业者、
      或蓝V认证且内容专业;(2) 评价有实质——涉及能力、对比、局限、基准等,而非一句空泛感叹。
- "news":关于该产品的资讯 / 发布 / 报道 / 转述,作者本人并未使用或评价。
- "promo":官方账号自己发布的内容,或明显的付费推广 / 营销话术 / 抽奖引流。
  这类不算独立第三方证据。若作者handle在官方账号列表中,倾向判为 promo。
- "irrelevant":与该产品无关,或"K3"等关键词命中了同名的其他事物(车、相机等)。

其他字段判据:
- relevant:该推文是否真的在讲这个目标产品(true/false)。同名歧义命中 → false + irrelevant。
- confidence:0.0-1.0,你对本次分类整体判断的置信度。
- sentiment:positive / neutral / negative。负面同样要如实标注,负面的专家评价对内部有价值。
- has_media_evidence:推文是否带有产出物级别的媒体/链接/代码证据(true/false)。
- author_credibility_signals:字符串数组,列出作者可信度线索(如 "前 OpenAI 研究员"、
  "10万粉技术博主"、"蓝V认证")。没有则空数组。
- quotable_excerpt:推文中最适合被引用的一句(保持原文语言,不要翻译)。若无则空字符串。
- summary_zh:一句话中文摘要。
- usable_for_marketing:该条是否适合市场直接引用(true/false)。demo/customer_case/
  正面且有实质的 expert_review 通常 true;promo/irrelevant/空泛内容通常 false;
  负面评价 usable_for_marketing 一般为 false(但仍要入库,内部参考)。
- usability_reason:一句话说明为什么适合 / 不适合市场引用。

输出的 JSON 必须且只能包含这些键:
relevant, category, confidence, sentiment, has_media_evidence,
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
