import os
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

SYSTEM_PROMPT = (
    "You are Patriot Lens, a serious and edgy conservative commentator on Twitter. "
    "Your mission: expose liberal bias and defend American values in a single, punchy tweet. "
    "Include two political hashtags. Keep under 280 characters."
)

def craft_tweet(headline: str) -> str:
    """Create an on-brand tweet for the provided news headline using the
    OpenAI chat completions API."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f'Headline: "{headline}"'}
    ]

    if _use_new_client:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=60,
            temperature=0.7,
        )
        tweet = response.choices[0].message.content.strip()
    else:
        response = client.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=60,
            temperature=0.7,
        )
        tweet = response["choices"][0]["message"]["content"].strip()

    return tweet[:280]