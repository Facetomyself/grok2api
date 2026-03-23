"""
OpenAI 兼容 usage 估算工具。

说明：
- Grok 网页逆向链路当前没有稳定暴露逐请求的 prompt/completion token 统计。
- 这里提供轻量本地估算，避免兼容客户端始终看到 0。
- 估算值仅用于展示与基础统计，不应视为精确计费结果。
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

import json


_TOKEN_SEGMENT_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_PROMPT_OVERHEAD_TOKENS = 4


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def estimate_tokens(value: Any) -> int:
    if value is None:
        return 0

    if isinstance(value, (bytes, bytearray)):
        if not value:
            return 0
        return max(1, math.ceil(len(value) / 4))

    if not isinstance(value, str):
        try:
            value = _compact_json(value)
        except Exception:
            value = str(value)

    text = value.strip()
    if not text:
        return 0

    byte_estimate = math.ceil(len(text.encode("utf-8")) / 4)
    segment_estimate = math.ceil(len(_TOKEN_SEGMENT_RE.findall(text)) * 0.75)
    return max(1, byte_estimate, segment_estimate)


def estimate_prompt_tokens(prompt_text: str) -> int:
    if not prompt_text or not prompt_text.strip():
        return 0
    return estimate_tokens(prompt_text) + _PROMPT_OVERHEAD_TOKENS


def estimate_completion_tokens(*, content: Optional[str] = None) -> int:
    return estimate_tokens(content)


def build_chat_usage(prompt_tokens: int, completion_tokens: int) -> Dict[str, Any]:
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens_details": {
            "cached_tokens": 0,
            "text_tokens": prompt_tokens,
            "audio_tokens": 0,
            "image_tokens": 0,
        },
        "completion_tokens_details": {
            "text_tokens": completion_tokens,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
        },
    }


def estimate_chat_usage(*, prompt_tokens: int, content: Optional[str] = None) -> Dict[str, Any]:
    completion_tokens = estimate_completion_tokens(content=content)
    return build_chat_usage(prompt_tokens, completion_tokens)


__all__ = [
    "build_chat_usage",
    "estimate_chat_usage",
    "estimate_completion_tokens",
    "estimate_prompt_tokens",
    "estimate_tokens",
]
