"""Pattern catalog and text matching."""

from __future__ import annotations

import re
from typing import Any

from core.storage import load_patterns

QUESTION_RE = re.compile(
    r"(?i)(?:^|\b)(?:what(?:'s|\s+is|\s+does|\s+do)|why(?:\s+do|\s+does|\s+are|\s+is|\s+not)?|how(?:\s+does|\s+do|\s+to|\s+can)?|explain|help me understand|can you explain|should i use|is it better|when should|what's the difference)",
)

REQUEST_VERBS_RE = re.compile(
    r"(?i)\b(?:add|use|implement|apply|introduce|switch to|refactor to|memoize|memoiz)\b",
)


def looks_like_learning_question(prompt: str) -> bool:
    if "?" in prompt and len(prompt.strip()) > 8:
        return True
    return QUESTION_RE.search(prompt) is not None


def compile_pattern_list(values: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for value in values:
        try:
            compiled.append(re.compile(value, re.IGNORECASE | re.MULTILINE))
        except re.error:
            continue
    return compiled


def load_pattern_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for item in load_patterns():
        slug = item.get("slug")
        if not slug:
            continue
        catalog.append(
            {
                "slug": slug,
                "title": item.get("title") or slug,
                "code_res": compile_pattern_list(item.get("code_regex") or []),
                "mention_res": compile_pattern_list(item.get("mention_regex") or []),
                "question_res": compile_pattern_list(item.get("question_regex") or []),
                "keywords": [str(k).lower() for k in (item.get("keywords") or [])],
            }
        )
    return catalog


def match_patterns(text: str, regexes: list[re.Pattern[str]]) -> bool:
    return any(regex.search(text) for regex in regexes)


def detect_patterns_in_text(text: str, mode: str) -> list[str]:
    slugs: list[str] = []
    lowered = text.lower()
    for item in load_pattern_catalog():
        regex_key = "code_res" if mode == "code" else "mention_res" if mode == "mention" else "question_res"
        if match_patterns(text, item[regex_key]):
            slugs.append(item["slug"])
            continue
        if mode == "question" and any(keyword in lowered for keyword in item["keywords"]):
            slugs.append(item["slug"])
    return sorted(set(slugs))


def prompt_requested_pattern(prompt: str, slug: str, keywords: list[str]) -> bool:
    lowered = prompt.lower()
    if any(keyword in lowered for keyword in keywords):
        return REQUEST_VERBS_RE.search(prompt) is not None or not looks_like_learning_question(prompt)
    return False


def slug_title(slug: str) -> str:
    for item in load_patterns():
        if item.get("slug") == slug:
            return str(item.get("title") or slug)
    return slug.split("/")[-1].replace("-", " ")


def trim_excerpt(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"
