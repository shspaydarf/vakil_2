"""Conservative, deterministic prompt-cost helpers.

Only formatting noise is removed. Legal wording, numbers, page markers, JSON
structure, order, and source text are never summarized or paraphrased here.
"""
from __future__ import annotations
import re
from typing import Any


def compact_content(value: Any) -> tuple[str, int]:
    text = str(value or '')
    if not text:
        return text, 0
    before = len(text)
    # Trailing spaces are not semantically meaningful in prompts.
    text = re.sub(r"[ \t]+(?=\r?$)", "", text, flags=re.M)
    # Three or more blank lines are reduced to two; paragraph boundaries remain.
    text = re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", text)
    return text, max(0, before - len(text))


def compact_messages(messages: Any) -> tuple[list, dict]:
    if not isinstance(messages, list):
        return messages, {"before_chars": 0, "after_chars": 0, "saved_chars": 0}
    output = []
    before = after = 0
    for message in messages:
        if not isinstance(message, dict):
            output.append(message)
            continue
        item = dict(message)
        content = item.get('content')
        if isinstance(content, str):
            before += len(content)
            item['content'], _ = compact_content(content)
            after += len(item['content'])
        elif isinstance(content, list):
            # Multimodal payloads are preserved exactly; only text blocks are compacted.
            blocks = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get('text'), str):
                    b = dict(block); before += len(b['text']); b['text'], _ = compact_content(b['text']); after += len(b['text']); blocks.append(b)
                else:
                    blocks.append(block)
            item['content'] = blocks
        output.append(item)
    return output, {"before_chars": before, "after_chars": after, "saved_chars": max(0, before-after)}


def estimate_tokens_from_chars(char_count: int) -> int:
    """Rough planning estimate only; provider-reported usage remains authoritative."""
    try:
        count = max(0, int(char_count))
    except (TypeError, ValueError):
        count = 0
    # Persian and mixed legal text vary significantly by tokenizer. This deliberately
    # errs toward a cautious estimate and is never used for billing or quota decisions.
    return (count + 1) // 2


def build_optimization_hints(report: dict) -> list[dict]:
    hints = []
    rows = report.get('by_feature') or []
    for row in rows[:5]:
        feature = str(row.get('feature') or 'unspecified')
        calls = int(row.get('calls') or 0)
        tokens = int(row.get('total_tokens') or 0)
        if calls >= 3 and tokens:
            hints.append({"feature": feature, "calls": calls, "total_tokens": tokens,
                          "hint": "این قابلیت را از نظر تکرار زمینه، اندازه ورودی و امکان استخراج محلی بررسی کنید."})
    if report.get('summary', {}).get('usage_reported_calls', 0) < report.get('summary', {}).get('calls', 0):
        hints.append({"feature": "provider_usage", "hint": "برای بخشی از درخواست‌ها ارائه‌دهنده آمار توکن نداده؛ تخمین نویسه‌ای جایگزین قبض واقعی نیست."})
    return hints
