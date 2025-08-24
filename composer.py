import os
import random
import re
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "python-dotenv package is required. Install dependencies from requirements.txt"
    ) from exc

try:
    # Prefer the new OpenAI client if available
    from openai import OpenAI
    _use_new_client = True
except ImportError:
    try:
        import openai
        _use_new_client = False
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "openai package is required. Install dependencies from requirements.txt"
        ) from exc

load_dotenv()

if _use_new_client:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    client = openai


# =========================
# Engagement-Oriented Config
# =========================

@dataclass
class TweetConfig:
    """
    Engagement-focused configuration for tweet generation.

    Why this helps engagement:
    - Lets you vary tone/length to avoid "botty" repetition.
    - Enables/limits hashtags to keep them sparing and on-brand.
    - Adds light randomization to boost perceived authenticity.
    """
    tone: str = "edgy, plain-spoken, confident"               # high-level vibe
    max_length: int = 280                                      # API hard limit
    max_hashtags: int = 1                                      # 'sparingly' by default
    allow_hashtags: bool = True
    use_questions_ratio: float = 0.35                          # curiosity + replies
    use_cta_ratio: float = 0.20                                # retweets/replies/follows
    include_emojis: bool = False                               # use sparingly; off by default
    trending_keywords: List[str] = field(default_factory=list) # inject from your scheduler if you fetch trends elsewhere
    brand_hashtags: List[str] = field(default_factory=lambda: ["#AmericaFirst"])
    # protect against spammy patterns:
    dedupe_window_keywords: int = 5                            # limit repeated topical tags across recent tweets (handled upstream if you store history)
    # output safety:
    strip_ai_markers: bool = True
    # LLM parameters:
    # Upgrading to GPT-4o sharpens wit and variety, yielding more shareable copy.
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 120


# =========================
# Brand Voice & Prompting
# =========================

# A sharpened but platform-safe system prompt that preserves your theme
# while optimizing for reach & authenticity (concise, readable, non-spammy).
SYSTEM_PROMPT = (
    "You are Patriot Lens—an edgy, sharp-tongued conservative commentator on Twitter "
    "who values rugged individualism, limited government, and America First priorities.\n\n"
    "Objectives:\n"
    "• Create concise, scannable tweets that maximize engagement (likes/replies/retweets/follows).\n"
    "• Preserve voice: bold, witty, pointed; no vulgarity; avoid clichés; avoid unsubstantiated conspiracy claims.\n"
    "• Use hooks, relatable phrasing, curiosity gaps, and—sparingly—hashtags.\n"
    "• Vary forms: headlines, insights, questions, conversation starters.\n"
    "• Keep under 280 chars; clear, readable; no walls of text.\n"
)

# Lightweight, reusable fragments that prompt the model to produce
# specific engagement-forward structures while keeping variety.
HOOKS = [
    "Quick hit",
    "Hard truth",
    "Worth asking",
    "Let’s be honest",
    "Numbers don’t lie",
    "Reality check",
    "Here’s the tell",
    "Watch this trend",
]

CTAS = [
    "Agree?",
    "Thoughts?",
    "Save this for later.",
    "Send this to a friend who should see it.",
    "If this tracks, say why.",
    "Bookmark this for the next debate.",
]

QUESTION_OPENERS = [
    "Be honest—",
    "Serious question—",
    "If this is 'normal,' why—",
    "What are we missing—",
    "So riddle me this—",
]


# =========================
# Hashtag & Keyword Mapping
# =========================

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


def _infer_topical_tags(text: str, limit: int, seed_tags: List[str]) -> List[str]:
    """
    Find relevant topical tags from headline/summary; backfill with brand/trending.

    Engagement rationale:
    - Keeps hashtags highly relevant and minimal (sparingly).
    - Allows you to inject current trends from your scheduler ingestion.
    """
    text_lc = (text or "").lower()
    tags = []
    for kw, tag in TOPICAL_KEYWORDS.items():
        if kw in text_lc and tag not in tags:
            tags.append(tag)

    # backfill with trending/brand tags (non-duplicates)
    for t in seed_tags:
        if t not in tags:
            tags.append(t)

    if not tags:
        tags = [GENERIC_NEWS_TAG]

    return tags[:max(0, limit)]


def _sanitize(text: str) -> str:
    """
    Remove common AI disclaimers and normalize punctuation.
    """
    text = text.replace("—", "-")
    if re.search(r"(?i)\bas an ai\b|\bi am an ai\b|\bas a language model\b", text):
        text = re.sub(r"(?i)as an ai[^.?!]*[.?!]?\s*", "", text)
        text = re.sub(r"(?i)i(?: am|'m) an ai[^.?!]*[.?!]?\s*", "", text)
        text = re.sub(r"(?i)as a language model[^.?!]*[.?!]?\s*", "", text)
    # collapse excessive punctuation / spaces
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([!?])\1{2,}", r"\1\1", text)   # no !!! spam
    text = re.sub(r"#([A-Za-z0-9_]{1,50})(?:\s*#\1)+", r"#\1", text)  # de-dupe repeated tag words
    return text


def _maybe_add_question(text: str, ratio: float) -> str:
    """
    Occasionally end with a short question to prompt replies.

    Engagement rationale:
    - Questions invite responses & boosts reply metrics.
    """
    if random.random() < ratio and not text.rstrip().endswith("?"):
        q = random.choice(QUESTION_OPENERS)
        # Ensure we stay concise:
        if len(text) + len(" " + q + " ?") <= 260:  # leave room for a tag
            return f"{text} {q}?"
    return text


def _maybe_add_cta(text: str, ratio: float) -> str:
    """
    Occasionally add a brief CTA.

    Engagement rationale:
    - CTAs nudge users to reply/bookmark/share without sounding spammy.
    """
    if random.random() < ratio:
        cta = random.choice(CTAS)
        if len(text) + len(" " + cta) <= 260:
            return f"{text} {cta}"
    return text


def _emoji_guard(text: str, allow: bool) -> str:
    """
    Allow or remove emojis based on config to keep style consistent.
    """
    if allow:
        return text
    return re.sub(r"[^\w\s.,:;/?@#'\-\(\)%!]", "", text)  # strip non-basic emoji/symbols


def _trim_to_length(base: str, tags: List[str], max_len: int) -> str:
    """
    Compose final tweet with tags and trim safely under character limit.
    """
    hashtag_str = ""
    if tags:
        hashtag_str = " " + " ".join(tags)
    avail = max_len - len(hashtag_str)
    base = base[:max(0, avail)].rstrip()
    return f"{base}{hashtag_str}"


def _build_messages(headline: str, summary: str, cfg: TweetConfig) -> List[dict]:
    """
    Builds the LLM messages with light structure cues for variety.

    Engagement rationale:
    - Hooks + concise structure improves scannability.
    - Explicit variety signals reduce repetitive outputs.
    """
    hook = random.choice(HOOKS)

    style_nudges = random.choice([
        "Format: hook + key detail + insight.",
        "Format: headline-style + one-liner takeaway.",
        "Format: counterintuitive insight + short reason.",
        "Format: question-led opener + quick punchline.",
        "Format: observation + comparison/metaphor.",
    ])

    user_prompt = (
        f"Headline: \"{headline}\"\n"
        f"Summary: \"{summary or ''}\"\n\n"
        f"Constraints:\n"
        f"- Start with a brief hook like \"{hook}:\" (no quotes).\n"
        f"- Tone: {cfg.tone}.\n"
        f"- Keep it under {cfg.max_length} chars; highly readable.\n"
        f"- Avoid clichés and walls of text; no vulgarity.\n"
        f"- Use relatable phrasing; one crisp detail if possible.\n"
        f"- {style_nudges}\n"
        f"- Vary sentence lengths. 1-2 short, 1 medium.\n"
        f"- Output a single tweet only.\n"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def craft_tweet(
    headline: str,
    summary: str = "",
    config: Optional[TweetConfig] = None
) -> str:
    """
    Create an on-brand, engagement-optimized tweet for the provided topic.

    Engagement-supporting behavior:
    - Hooks/questions/CTAs added stochastically to prompt conversation.
    - Hashtags kept minimal & relevant to avoid spammy feel.
    - Strict 280-char enforcement with clean text sanitation.
    """
    cfg = config or TweetConfig()

    # Build messages for the LLM with variety & clarity baked in.
    messages = _build_messages(headline, summary, cfg)

    # Call OpenAI with either the new or legacy client
    if _use_new_client:
        resp = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
        )
        text = resp.choices[0].message.content.strip()
    else:
        resp = client.ChatCompletion.create(
            model=cfg.model,
            messages=messages,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
        )
        text = resp["choices"][0]["message"]["content"].strip()

    # Post-process for platform polish & engagement:
    text = _sanitize(text)
    text = _maybe_add_question(text, cfg.use_questions_ratio)
    text = _maybe_add_cta(text, cfg.use_cta_ratio)
    text = _emoji_guard(text, cfg.include_emojis)

    # Hashtags (sparingly) — combine topical + scheduler-provided trending + brand
    tags: List[str] = []
    if cfg.allow_hashtags and cfg.max_hashtags > 0:
        seed = list(dict.fromkeys(cfg.trending_keywords + cfg.brand_hashtags))
        topical = _infer_topical_tags(
            text=(headline or "") + " " + (summary or ""),
            limit=cfg.max_hashtags,
            seed_tags=seed
        )
        # De-duplicate and keep order
        tags = list(dict.fromkeys([t for t in topical if t.startswith("#")][:cfg.max_hashtags]))

    # Final length guard with tags appended:
    final_tweet = _trim_to_length(text, tags, cfg.max_length)
    return final_tweet


# ==============
# Quick Smoke Test
# ==============
if __name__ == "__main__":
    sample_cfg = TweetConfig(
        max_hashtags=1,
        allow_hashtags=True,
        trending_keywords=["#Economy"],  # e.g., injected by your scheduler layer
        include_emojis=False,
    )
    sample = craft_tweet(
        "Senate approves a $1.5T spending bill with no border security",
        "Massive government spending continues with zero commitment to border protections.",
        config=sample_cfg
    )
    print("🔹 Sample tweet:\n", sample)
