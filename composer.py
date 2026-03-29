"""Tweet composer for Patriot Lens Bot.

Generates engagement-optimised tweet copy via OpenAI's chat API.
Supports three formats:
  - "single"         — one standalone tweet (default)
  - "question_cta"   — tweet ending with a reply-driving question
  - "numbered_thread"— use craft_thread_pair() instead of craft_tweet()
"""
from __future__ import annotations

import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "python-dotenv is required. Run: pip install -r requirements.txt"
    ) from exc

try:
    from openai import OpenAI
    _use_new_client = True
except ImportError:
    try:
        import openai
        _use_new_client = False
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "openai is required. Run: pip install -r requirements.txt"
        ) from exc

load_dotenv()

DEFAULT_TWEET_MODEL = os.getenv("OPENAI_TWEET_MODEL", "gpt-4o-mini")
FALLBACK_TWEET_MODELS = [
    m.strip()
    for m in os.getenv("OPENAI_TWEET_MODEL_FALLBACKS", "gpt-4o,gpt-4.1-mini").split(",")
    if m.strip()
]

if _use_new_client:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    client = openai


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class TweetConfig:
    """Engagement-focused configuration for tweet generation."""

    tone: str = "edgy, plain-spoken, confident"
    max_length: int = 280
    max_hashtags: int = 2          # 1-2 at the END; never mid-tweet
    allow_hashtags: bool = True
    use_questions_ratio: float = 0.35
    use_cta_ratio: float = 0.20
    include_emojis: bool = False
    trending_keywords: List[str] = field(default_factory=list)
    brand_hashtags: List[str] = field(default_factory=lambda: ["#AmericaFirst"])
    strip_ai_markers: bool = True
    model: str = DEFAULT_TWEET_MODEL
    temperature: float = 1.0
    max_completion_tokens: int = 200
    max_tokens: Optional[int] = None   # legacy alias
    candidate_count: int = 6

    def __post_init__(self) -> None:
        if self.max_tokens is not None:
            self.max_completion_tokens = self.max_tokens


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are Patriot Lens, a bold conservative commentator on Twitter/X.\n\n"
    "HARD RULES — follow every one:\n"
    "1. Use active voice and strong verbs. Eliminate all passive constructions.\n"
    "2. Never use em-dashes (—). Use a comma or period instead.\n"
    "3. Never open with filler phrases: 'Let's be clear', 'Make no mistake', "
    "'At the end of the day', 'Look,', 'Folks,', 'Here's the thing'.\n"
    "4. No hashtags inside the tweet body. Hashtags belong at the very end only.\n"
    "5. No vulgarity. No unsubstantiated conspiracy claims.\n"
    "6. Stay under 260 characters (hashtags are appended separately).\n"
    "7. Output ONLY the tweet text. No quotes around it, no labels, no explanation.\n\n"
    "STYLE:\n"
    "- Drop in one concrete fact or number when available.\n"
    "- Mix short punchy sentences with one medium one.\n"
    "- Be witty and pointed, not angry or ranty.\n"
    "- You value America First priorities, limited government, and rugged individualism.\n"
)

THREAD_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + "\nYou are writing one tweet in a 2-tweet thread. "
    "Each tweet must stand alone and be under 280 characters.\n"
)


# ---------------------------------------------------------------------------
# Format-specific instructions
# ---------------------------------------------------------------------------

_FORMAT_STYLES = {
    "bold_statement": (
        "Write a single bold declarative statement. Lead with the strongest "
        "claim. Use present tense where possible."
    ),
    "breaking": (
        "Start the tweet with 'BREAKING:' then give a tight, urgent summary "
        "of what happened and why it matters. Maximum urgency, minimum words."
    ),
    "rhetorical_question": (
        "Open with a short rhetorical question that reframes the headline from "
        "a skeptical angle, then give a one-sentence implication or answer."
    ),
    "question_cta": (
        "Make a bold observation about the story. End with a direct question "
        "to drive replies, such as 'Agree or disagree?' or 'What do you think?'. "
        "Do NOT end with a period after the question mark."
    ),
}

_URGENCY_WORDS = frozenset(
    {"breaking", "just in", "confirmed", "alert", "massive", "unprecedented"}
)

_STYLE_ANGLES = [
    "Lead with a punchy comparison and one concrete detail.",
    "Lead with a trend observation and a skeptical takeaway.",
    "Lead with a contradiction and one sentence of context.",
    "Lead with a plain-language consequence for everyday Americans.",
    "Lead with a data point and an opinionated conclusion.",
    "Lead with a short challenge statement and one-line rationale.",
]

_QUESTION_CTAS = [
    "Agree or disagree?",
    "What do you think?",
    "Sound off below.",
    "Change my mind.",
]


# ---------------------------------------------------------------------------
# Hashtag mapping
# ---------------------------------------------------------------------------

TOPICAL_KEYWORDS = {
    "border": "#BorderSecurity",
    "immigration": "#BorderSecurity",
    "spending": "#Inflation",
    "debt": "#Economy",
    "tax": "#Taxes",
    "crime": "#LawAndOrder",
    "police": "#LawAndOrder",
    "education": "#Education",
    "gender": "#ParentsMatter",
    "climate": "#Energy",
    "energy": "#Energy",
    "fossil": "#Energy",
    "gun": "#2A",
    "second amendment": "#2A",
    "censorship": "#FreeSpeech",
    "social media": "#FreeSpeech",
    "election": "#ElectionIntegrity",
    "voting": "#ElectionIntegrity",
    "china": "#China",
    "ukraine": "#ForeignPolicy",
    "israel": "#ForeignPolicy",
    "patriot": "#AmericaFirst",
    "military": "#NationalSecurity",
    "student loan": "#Economy",
    "covid": "#PublicHealth",
    "mask": "#PublicHealth",
    "vaccine": "#PublicHealth",
    "mandate": "#PublicHealth",
    "biden": "#Politics",
    "trump": "#Politics",
    "gas": "#Economy",
    "iran": "#ForeignPolicy",
}

GENERIC_NEWS_TAG = "#News"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_urgency(headline: str) -> bool:
    lc = headline.lower()
    return any(w in lc for w in _URGENCY_WORDS)


def _choose_format_style(headline: str, tweet_format: str) -> str:
    """Pick a format style string based on requested format and headline content."""
    if tweet_format == "question_cta":
        return "question_cta"
    if _has_urgency(headline):
        return "breaking"
    # Weight bold_statement 2:1 over rhetorical_question for variety
    return random.choice(["bold_statement", "bold_statement", "rhetorical_question"])


def _infer_topical_tags(text: str, limit: int, seed_tags: List[str]) -> List[str]:
    text_lc = (text or "").lower()
    tags: List[str] = []
    for kw, tag in TOPICAL_KEYWORDS.items():
        if kw in text_lc and tag not in tags:
            tags.append(tag)
    for t in seed_tags:
        if t not in tags:
            tags.append(t)
    if not tags:
        tags = [GENERIC_NEWS_TAG]
    return tags[: max(0, limit)]


def _sanitize(text: str) -> str:
    """Strip AI disclaimers, em-dashes, and normalize whitespace."""
    # Replace em-dashes with comma+space or period based on context
    text = re.sub(r"\s*—\s*", ", ", text)
    # Strip AI self-references
    if re.search(r"(?i)\bas an ai\b|\bi am an ai\b|\bas a language model\b", text):
        text = re.sub(r"(?i)as an ai[^.?!]*[.?!]?\s*", "", text)
        text = re.sub(r"(?i)i(?: am|'m) an ai[^.?!]*[.?!]?\s*", "", text)
        text = re.sub(r"(?i)as a language model[^.?!]*[.?!]?\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([!?])\1{2,}", r"\1\1", text)
    text = re.sub(r"#([A-Za-z0-9_]{1,50})(?:\s*#\1)+", r"#\1", text)
    return text


def _ensure_question_cta(text: str) -> str:
    """Guarantee the text ends with a reply-driving question if it doesn't already."""
    text = text.rstrip()
    if text.endswith("?"):
        return text
    cta = random.choice(_QUESTION_CTAS)
    budget = 260 - len(" " + cta)
    if len(text) <= budget:
        return f"{text} {cta}"
    # Trim body to fit
    trimmed = text[:budget].rsplit(" ", 1)[0]
    return f"{trimmed} {cta}"


def _emoji_guard(text: str, allow: bool) -> str:
    if allow:
        return text
    return re.sub(r"[^\w\s.,:;/?@#'\-\(\)%!]", "", text)


def _trim_to_length(base: str, tags: List[str], max_len: int, url: str = "") -> str:
    """Compose final tweet under max_len without cutting URL/hashtags."""
    suffix_parts: List[str] = []
    if url:
        suffix_parts.append(url.strip())
    if tags:
        suffix_parts.extend(tags)

    suffix = ""
    if suffix_parts:
        suffix = " " + " ".join(p for p in suffix_parts if p)

    avail = max_len - len(suffix)
    if avail < 0:
        kept: List[str] = []
        for token in suffix_parts:
            candidate = " ".join(kept + [token])
            if len(candidate) <= max_len:
                kept.append(token)
        suffix = (" " + " ".join(kept)) if kept else ""
        avail = max_len - len(suffix)

    trimmed_base = base[: max(0, avail)].rstrip()
    return f"{trimmed_base}{suffix}".strip()[:max_len]


def _build_messages(
    headline: str,
    summary: str,
    cfg: TweetConfig,
    format_style: str,
) -> List[dict]:
    """Build LLM messages for a single tweet."""
    format_instruction = _FORMAT_STYLES.get(format_style, _FORMAT_STYLES["bold_statement"])
    style_nudge = random.choice(_STYLE_ANGLES)

    user_prompt = (
        f'Headline: "{headline}"\n'
        f'Summary: "{summary or ""}"\n\n'
        f"Format instruction: {format_instruction}\n"
        f"Additional style nudge: {style_nudge}\n\n"
        f"Tone: {cfg.tone}.\n"
        f"Max length: 260 characters (no hashtags in body).\n"
        f"Output ONLY the tweet text.\n"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _build_thread_messages(
    headline: str,
    summary: str,
    cfg: TweetConfig,
    tweet_num: int,
    hook_text: str = "",
) -> List[dict]:
    """Build LLM messages for one tweet in a 2-tweet thread."""
    if tweet_num == 1:
        instruction = (
            "Write tweet 1 of 2. This is the HOOK: a punchy, provocative opener that "
            "makes readers want to see tweet 2. Strong claim or rhetorical question. "
            "Under 260 characters. No hashtags."
        )
        context = f'Headline: "{headline}"\nSummary: "{summary or ""}"\n'
    else:
        instruction = (
            "Write tweet 2 of 2. This is the CONTEXT: give 3-4 tight sentences of "
            "background and implication. Reference the hook tweet below. "
            "Under 270 characters. No hashtags."
        )
        context = (
            f'Headline: "{headline}"\n'
            f'Summary: "{summary or ""}"\n'
            f'Hook tweet (tweet 1): "{hook_text}"\n'
        )

    user_prompt = (
        f"{context}\n"
        f"Instruction: {instruction}\n"
        f"Tone: {cfg.tone}.\n"
        f"Output ONLY the tweet text.\n"
    )
    return [
        {"role": "system", "content": THREAD_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# ---------------------------------------------------------------------------
# LLM call with model fallback
# ---------------------------------------------------------------------------

def _supports_custom_temperature(model_name: str) -> bool:
    return not model_name.lower().startswith("gpt-5")


def _generate_candidate(messages: List[dict], cfg: TweetConfig) -> str:
    """Generate one candidate tweet; tries model list in priority order."""
    models = [cfg.model] + [m for m in FALLBACK_TWEET_MODELS if m != cfg.model]
    last_error: Optional[Exception] = None

    for model_name in models:
        sampled_temp = min(1.1, max(0.35, cfg.temperature + random.uniform(-0.18, 0.15)))
        allow_temp = _supports_custom_temperature(model_name)
        try:
            if _use_new_client:
                kwargs: dict = {"model": model_name, "messages": messages}
                if allow_temp:
                    kwargs["temperature"] = sampled_temp
                try:
                    resp = client.chat.completions.create(
                        **kwargs, max_completion_tokens=cfg.max_completion_tokens
                    )
                except TypeError as te:
                    if "max_completion_tokens" not in str(te):
                        raise
                    resp = client.chat.completions.create(
                        **kwargs, max_tokens=cfg.max_completion_tokens
                    )
                except Exception as e:
                    if "temperature" not in str(e).lower():
                        raise
                    kwargs.pop("temperature", None)
                    try:
                        resp = client.chat.completions.create(
                            **kwargs, max_completion_tokens=cfg.max_completion_tokens
                        )
                    except TypeError:
                        resp = client.chat.completions.create(
                            **kwargs, max_tokens=cfg.max_completion_tokens
                        )
                content = (resp.choices[0].message.content or "").strip()
                if not content:
                    refusal = getattr(resp.choices[0].message, "refusal", None)
                    logger.warning(
                        "Model %s returned empty content%s; trying fallback",
                        model_name,
                        f" (refusal: {refusal[:80]})" if refusal else "",
                    )
                    last_error = ValueError(f"{model_name} returned empty content")
                    continue
                return content

            # Legacy client path
            lkw: dict = {
                "model": model_name,
                "messages": messages,
                "max_tokens": cfg.max_completion_tokens,
            }
            if allow_temp:
                lkw["temperature"] = sampled_temp
            try:
                resp = client.ChatCompletion.create(**lkw)
            except Exception as e:
                if "temperature" not in str(e).lower():
                    raise
                lkw.pop("temperature", None)
                resp = client.ChatCompletion.create(**lkw)
            return resp["choices"][0]["message"]["content"].strip()

        except Exception as exc:
            err = str(exc).lower()
            if "model_not_found" in err or "does not exist" in err or "access" in err:
                last_error = exc
                continue
            raise

    raise RuntimeError(
        f"No accessible tweet model. Tried: {', '.join(models)}"
    ) from last_error


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------

def _score_candidate(text: str, headline: str, summary: str, cfg: TweetConfig) -> float:
    """Heuristic scoring to prefer specific, varied, readable candidates."""
    score = 0.0
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    unique_ratio = (len(set(words)) / len(words)) if words else 0.0
    score += unique_ratio * 2.5

    char_len = len(text)
    if 95 <= char_len <= 235:
        score += 1.5
    elif char_len < 60:
        score -= 1.0
    elif char_len > cfg.max_length:
        score -= 3.0

    if "?" in text:
        score += 0.25
    if re.search(r"\b(why|how|what|when)\b", text.lower()):
        score += 0.2

    source = f"{headline} {summary}".lower()
    overlap = sum(1 for w in set(words) if len(w) > 4 and w in source)
    score += min(2.0, overlap * 0.2)

    if re.search(r"([!?])\1{2,}", text):
        score -= 0.4

    # Penalise banned filler openers
    lc = text.lower()
    for filler in ("let's be clear", "make no mistake", "at the end of the day", "look,"):
        if lc.startswith(filler):
            score -= 1.5

    return score


# ---------------------------------------------------------------------------
# Combined cleaning helper
# ---------------------------------------------------------------------------

def _clean_llm_output(text: str, allow_emojis: bool) -> str:
    """Sanitize and strip LLM formatting artifacts in one pass.

    Handles:
    - Wrapper double-quotes the model sometimes adds around the tweet
    - Markdown code fences (``` ... ```)
    - Leading labels like "Tweet:" or "Here is the tweet:"
    - em-dashes, AI disclaimers, excess punctuation
    - Emoji (when allow_emojis=False) — but preserves the text body
    """
    if not text:
        return ""

    # Strip markdown code fences
    text = re.sub(r"^```[^\n]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())

    # Strip common LLM preamble labels
    text = re.sub(
        r"(?i)^(tweet\s*:?|here(?:'s| is)(?: the| your)?\s*tweet\s*:?)\s*",
        "",
        text.strip(),
    )

    # Strip surrounding double-quotes the model adds (both straight and curly)
    text = re.sub(r'^["\u201c](.*)["\u201d]$', r"\1", text.strip(), flags=re.DOTALL)

    # Standard sanitization (em-dashes, AI disclaimers, whitespace)
    text = _sanitize(text)

    # Emoji guard — only strip non-standard chars, NOT alphanumerics or punctuation
    if not allow_emojis:
        # More permissive than before: keep curly quotes as straight equivalents
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        # Now strip true non-text characters (emoji, symbols) but keep punctuation
        text = re.sub(r"[^\w\s.,:;!?@#'\"\-\(\)%&]", "", text)

    # Strip hashtags from the body — we append our own curated tags at the end
    text = re.sub(r"\s*#\w+", "", text).strip()

    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def craft_tweet(
    headline: str,
    summary: str = "",
    url: str = "",
    config: Optional[TweetConfig] = None,
    tweet_format: str = "single",
) -> str:
    """Craft an on-brand, engagement-optimised tweet.

    Args:
        headline:     News headline to riff on.
        summary:      Optional article description for additional context.
        url:          Optional URL appended after hashtags (counts toward length).
        config:       TweetConfig instance; uses defaults if None.
        tweet_format: "single" | "question_cta".  For "numbered_thread" use
                      :func:`craft_thread_pair` instead.

    Returns:
        Ready-to-post tweet string <= 280 characters.
    """
    cfg = config or TweetConfig()
    format_style = _choose_format_style(headline, tweet_format)

    candidate_count = max(1, cfg.candidate_count)
    candidates: List[Tuple[float, str]] = []

    for _ in range(candidate_count):
        messages = _build_messages(headline, summary, cfg, format_style)
        raw = _generate_candidate(messages, cfg)
        logger.debug("LLM raw output: %r", raw)
        cleaned = _clean_llm_output(raw, cfg.include_emojis)

        if tweet_format == "question_cta":
            cleaned = _ensure_question_cta(cleaned)

        scored = _score_candidate(cleaned, headline, summary, cfg)
        candidates.append((scored, cleaned))

    candidates.sort(key=lambda c: c[0], reverse=True)
    text = candidates[0][1]

    text = _clean_llm_output(text, cfg.include_emojis)

    # Last-resort fallback: never send a blank tweet
    if not text:
        logger.warning("craft_tweet produced empty text after cleaning; falling back to headline")
        text = _sanitize(headline[:260])

    # Hashtags: inferred from content + brand, placed at end
    tags: List[str] = []
    if cfg.allow_hashtags and cfg.max_hashtags > 0:
        seed = list(dict.fromkeys(cfg.trending_keywords + cfg.brand_hashtags))
        topical = _infer_topical_tags(
            text=f"{headline} {summary}",
            limit=cfg.max_hashtags,
            seed_tags=seed,
        )
        tags = list(dict.fromkeys(t for t in topical if t.startswith("#")))[: cfg.max_hashtags]

    return _trim_to_length(text, tags, cfg.max_length, url=url)


def craft_thread_pair(
    headline: str,
    summary: str = "",
    url: str = "",
    config: Optional[TweetConfig] = None,
) -> Tuple[str, str]:
    """Craft a 2-tweet thread: (hook_tweet, context_tweet).

    Tweet 1 (hook):    punchy opener, < 260 chars.
    Tweet 2 (context): 3-4 sentences of background, <= 280 chars.
    Used exclusively for the 9 PM numbered_thread slot.
    """
    cfg = config or TweetConfig()

    # Tweet 1: hook (try multiple candidates, pick highest scored)
    hook_candidates: List[Tuple[float, str]] = []
    for _ in range(max(1, cfg.candidate_count // 2)):
        msgs = _build_thread_messages(headline, summary, cfg, tweet_num=1)
        raw = _generate_candidate(msgs, cfg)
        cleaned = _emoji_guard(_sanitize(raw), cfg.include_emojis)[:260]
        hook_candidates.append((_score_candidate(cleaned, headline, summary, cfg), cleaned))

    hook_candidates.sort(key=lambda c: c[0], reverse=True)
    hook = hook_candidates[0][1]

    # Tweet 2: context, referencing the chosen hook
    context_candidates: List[Tuple[float, str]] = []
    for _ in range(max(1, cfg.candidate_count // 2)):
        msgs = _build_thread_messages(headline, summary, cfg, tweet_num=2, hook_text=hook)
        raw = _generate_candidate(msgs, cfg)
        cleaned = _emoji_guard(_sanitize(raw), cfg.include_emojis)[:280]
        context_candidates.append((_score_candidate(cleaned, headline, summary, cfg), cleaned))

    context_candidates.sort(key=lambda c: c[0], reverse=True)
    context = context_candidates[0][1]

    # Append hashtags to the context tweet (tweet 2 carries the tags)
    tags: List[str] = []
    if cfg.allow_hashtags and cfg.max_hashtags > 0:
        seed = list(dict.fromkeys(cfg.trending_keywords + cfg.brand_hashtags))
        topical = _infer_topical_tags(
            text=f"{headline} {summary}",
            limit=cfg.max_hashtags,
            seed_tags=seed,
        )
        tags = list(dict.fromkeys(t for t in topical if t.startswith("#")))[: cfg.max_hashtags]

    context = _trim_to_length(context, tags, 280, url=url)
    return (hook, context)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = TweetConfig(max_hashtags=2, allow_hashtags=True, include_emojis=False)

    print("=== single ===")
    print(craft_tweet(
        "Senate approves $1.5T spending bill with zero border security measures",
        "Massive government spending bill passes with no border protections attached.",
        config=cfg,
        tweet_format="single",
    ))

    print("\n=== question_cta ===")
    print(craft_tweet(
        "BREAKING: DOJ drops charges against former officials",
        "Department of Justice announces it will not pursue charges.",
        config=cfg,
        tweet_format="question_cta",
    ))

    print("\n=== numbered_thread ===")
    t1, t2 = craft_thread_pair(
        "Confirmed: Fed raises rates for the fifth time this year",
        "Federal Reserve votes 7-2 to raise interest rates another 25 basis points.",
        config=cfg,
    )
    print(f"Tweet 1: {t1}")
    print(f"Tweet 2: {t2}")
