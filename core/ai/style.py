"""Style sample sanitization, preparation, and profile analysis."""

import copy
import re
from collections import Counter
from functools import lru_cache

from ..sanitize import sanitize_text

# Compiled once at import time instead of per analyze_style call.
latin_word_re = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*|\d+(?:\.\d+)?")
chinese_run_re = re.compile(r"[\u4e00-\u9fff]{2,}")


def sanitize_style_sample(text: str) -> str:
    """Remove secrets and quoted context before style learning."""
    return sanitize_text(text)


def prepare_style_samples(samples, limit=80):
    """Sanitize, deduplicate, and diversify samples for model prompts."""
    prepared = []
    seen = set()
    repeated_run = None
    run_count = 0
    for raw in samples or []:
        sample = sanitize_style_sample(raw)
        if not sample or sample in seen:
            continue
        if sample == repeated_run:
            run_count += 1
            if run_count > 2:
                continue
        else:
            repeated_run = sample
            run_count = 1
        seen.add(sample)
        prepared.append(sample)
    if len(prepared) <= limit:
        return prepared
    indexes = [round(i * (len(prepared) - 1) / (limit - 1))
               for i in range(limit)]
    return [prepared[i] for i in indexes]


def build_style_profile(samples):
    """Build distribution-oriented style facts for the system prompt."""
    clean = prepare_style_samples(samples, limit=2000)
    if not clean:
        return {
            "count": 0, "avg_length": 0, "length_distribution": {},
            "short_ratio": 0, "repeat_ratio": 0, "top_words": [],
            "punctuation": {}, "punctuation_ratio": 0,
            "emoji_ratio": 0,
        }
    lengths = [len(s) for s in clean]
    buckets = {"短(1-6)": 0, "中(7-20)": 0, "长(21+)": 0}
    for length in lengths:
        if length <= 6:
            buckets["短(1-6)"] += 1
        elif length <= 20:
            buckets["中(7-20)"] += 1
        else:
            buckets["长(21+)"] += 1
    stats = analyze_style(clean)
    unique_count = len(set(clean))
    all_text = "".join(clean)
    punct_total = sum(stats["punctuation"].values())
    return {
        **stats,
        "length_distribution": buckets,
        "short_ratio": round(buckets["短(1-6)"] / len(clean), 2),
        "repeat_ratio": round(1 - unique_count / len(clean), 2),
        "punctuation_ratio": round(punct_total / max(len(all_text), 1), 3),
    }


def analyze_style(samples):
    """Compute style statistics from a list of message strings.

    Samples are sanitized before any statistics are computed, and the
    sanitized result is cached keyed on the exact sample content, so
    adding/removing/editing samples invalidates the cache automatically.
    """
    samples = [sanitize_style_sample(s) for s in samples or []]
    samples = [s for s in samples if s]
    return copy.deepcopy(_analyze_style_cached(tuple(samples)))


@lru_cache(maxsize=8)
def _analyze_style_cached(samples):
    """Compute style statistics from an already-sanitized tuple of samples."""
    if not samples:
        return {
            "count": 0,
            "avg_length": 0,
            "top_words": [],
            "punctuation": {},
            "emoji_ratio": 0,
        }

    total_chars = sum(len(s) for s in samples)
    avg_length = total_chars / len(samples)

    all_text = "".join(samples)
    term_counts = Counter()

    for sample in samples:
        text = str(sample).strip()
        for token in latin_word_re.findall(text):
            if len(token) >= 2:
                term_counts[token.lower()] += 1
        for run in chinese_run_re.findall(text):
            max_size = min(8, len(run))
            for size in range(2, max_size + 1):
                for start in range(len(run) - size + 1):
                    term_counts[run[start : start + size]] += 1

    def choose_terms(candidates, limit, selected):
        candidates = sorted(
            candidates,
            key=lambda item: (item[1], len(item[0])),
            reverse=True,
        )
        for term, count in candidates:
            if len(selected) >= limit:
                break
            if any(term in picked for picked in selected):
                continue
            selected.append(term)

    top_words = []
    choose_terms(
        [item for item in term_counts.items()
         if len(item[0]) >= 3 and item[1] >= 2],
        7,
        top_words,
    )
    choose_terms(
        [item for item in term_counts.items()
         if len(item[0]) == 2 and item[1] >= 3]
        + [item for item in term_counts.items()
           if item[0].isascii() and item[1] >= 2],
        10,
        top_words,
    )

    punct_chars = "。，！？、；：""''…—"
    punct_counts = {}
    for p in punct_chars:
        count = all_text.count(p)
        if count > 0:
            punct_counts[p] = count

    emoji_count = 0
    for s in samples:
        for ch in s:
            cp = ord(ch)
            if (0x1F600 <= cp <= 0x1F64F) or (0x1F300 <= cp <= 0x1F5FF):
                emoji_count += 1
    emoji_ratio = emoji_count / len(samples) if samples else 0

    return {
        "count": len(samples),
        "avg_length": round(avg_length, 1),
        "top_words": top_words,
        "punctuation": punct_counts,
        "emoji_ratio": round(emoji_ratio, 2),
    }


__all__ = [
    "sanitize_style_sample",
    "prepare_style_samples",
    "build_style_profile",
    "analyze_style",
]

