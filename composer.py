import os
import random
from dotenv import load_dotenv

try:
    # Prefer the new OpenAI client if available
    from openai import OpenAI
    _use_new_client = True
except ImportError:  # Fall back to old API
    import openai
    _use_new_client = False

load_dotenv()

if _use_new_client:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    client = openai

# A concise system prompt defining the persona & constraints
SYSTEM_PROMPT = (
    "You are Patriot Lens, a serious, unapologetically edgy conservative commentator on Twitter. "
    "Mission: expose liberal bias and defend American values in one punchy tweet. "
    "Style: confident, declarative language. Respond with a single short statement and no hashtags. "
    "Begin with a brief 3-6 word phrase summarizing the article's topic (not a direct quote) followed by a colon. "
    "Keep the entire response under 240 characters so additional hashtags can be appended later."
)

# Two few-shot examples to teach the format
EXAMPLES = [
    {
        "role": "user",
        "content": 'Input: "City council bans patriotic flags at public rallies."'
    },
    {
        "role": "assistant",
        "content": (
            "They censor our flag today, they'll censor our speech tomorrow. "
            "Stand up for true patriotism!"
        )
    },
    {
        "role": "user",
        "content": 'Input: "New tax plan hikes rates on middle-class families."'
    },
    {
        "role": "assistant",
        "content": (
            "They promise fairness while squeezing hardworking Americans. "
            "Who really wins here?"
        )
    }
]

def craft_tweet(headline: str, topical_tag: str) -> str:
    """Create an on-brand tweet for the provided news headline."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *EXAMPLES,
        {
            "role": "user",
            "content": (
                f'Input: "{headline}"\n'
                "Guideline: start with a 3-6 word topic summary, not a quote,"
                " then your comment. Output:"
            ),
        }
    ]

    if _use_new_client:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=60,
            temperature=0.7,
        )
        tweet = resp.choices[0].message.content.strip()
    else:
        resp = client.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=60,
            temperature=0.7,
        )
        tweet = resp["choices"][0]["message"]["content"].strip()

    high_tags = ["#tcot", "#AmericaFirst", "#RedWave2026", "#SaveAmerica"]
    primary_tag = random.choice(high_tags)
    hashtags = " ".join([primary_tag, topical_tag])

    avail_len = 280 - len(hashtags) - 1  # space before hashtags
    tweet = tweet[:avail_len].strip()

    final_tweet = f"{tweet} {hashtags}".strip()

    return final_tweet

# Quick smoke-test
if __name__ == "__main__":
    sample = craft_tweet(
        "Senate approves a $1.5T spending bill with no border security",
        "#Inflation"
    )
    print("🔹 Sample tweet:\n", sample)