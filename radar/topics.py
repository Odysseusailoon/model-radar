"""Explainable topic hints, not factual validation or sentiment judgments."""
import re

RULES = {
    "performance": r"\b(throughput|latency|ttft|tpot|benchmark|tokens?[/ ](?:sec|s)\b|speedup|faster)\b",
    "pricing": r"\b(pricing|price cuts?|discounts?|cheaper|credits?)\b|\bper (?:million|1m|token|gpu.hour)\b",
    "model_availability": r"\b(releas(?:e|ed)|launch(?:ed)?|weights|available|support(?:s|ed)?)\b",
    "hardware_capacity": r"\b(gpus?|clusters?|capacity|blackwell|rubin|h100|h200|b200|b300|mi300x|mi350x|tpu)\b",
    "adoption": r"\b(customers?|production|deploy(?:ed|ment)?|migrat(?:e|ed|ion)|switch(?:ed|ing))\b",
    "partnership_claim": r"\b(partner(?:ship|s)?|collaborat(?:e|ion|ing)|integrat(?:e|ion|ed))\b",
    "reliability": r"\b(outage|downtime|incident|regression|rate.limit|reliability|broken)\b",
    "funding": r"\b(funding|financing|raised|series [a-f]|investment|ipo|valuation|market cap)\b",
}


def topic_tags(text):
    tags = [name for name, pattern in RULES.items() if re.search(pattern, text, re.I)]
    if "pricing" not in tags and re.search(r"\b(inference|tokens?|gpus?|serverless)\b", text, re.I) and re.search(r"\b(prices?|costs?)\b", text, re.I):
        tags.append("pricing")
    return tags
