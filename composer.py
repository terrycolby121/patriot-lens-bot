import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = (
    "You are Patriot Lens, a serious and edgy conservative commentator on Twitter. "
    "Your mission: expose liberal bias and defend American values in a single, punchy tweet. "
    "Include two hashtags (e.g. #tcot). Keep under 280 characters."
)

def craft_tweet(headline: str) -> str:
    """Create an on-brand tweet for the provided news headline using the
    OpenAI chat completions API."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f'Headline: "{headline}"'}
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=60,
        temperature=0.7,
    )

    tweet = response.choices[0].message.content.strip()
    return tweet[:280]

if __name__ == "__main__":
    # 1) Pick any headline you like
    test_headline = "Senate approves new spending bill that raises taxes on small businesses"
    # 2) Generate the on-brand tweet
    sample_tweet = craft_tweet(test_headline)
    # 3) Print it
    print("\n🔹 Sample PatriotLens tweet:\n", sample_tweet)

