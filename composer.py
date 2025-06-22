import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "tiiuae/falcon-7b"

# Load once at startup
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model     = AutoModelForCausalLM.from_pretrained(
               MODEL_ID,
               torch_dtype=torch.float16,
               device_map="auto",
            )

SYSTEM_PROMPT = (
    "You are Patriot Lens, a serious and edgy conservative commentator on Twitter. "
    "Your mission: expose liberal bias and defend American values in a single, punchy tweet. "
    "Include two hashtags (e.g. #tcot). Keep under 280 characters."
)

def craft_tweet(headline: str, summary: str = "") -> str:
    """Compose a tweet using both the headline and summary for context."""
    # Build the chat-style prompt
    prompt = f"{SYSTEM_PROMPT}\n\nHeadline: \"{headline}\""
    if summary:
        prompt += f"\nSummary: \"{summary}\""
    prompt += "\nTweet:"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    out = model.generate(
        **inputs,
        max_new_tokens=60,
        temperature=0.7,
        do_sample=True,
        top_p=0.9
    )
    text = tokenizer.decode(out[0], skip_special_tokens=True)
    # Extract only what comes after "Tweet:"
    tweet = text.split("Tweet:")[-1].strip()
    return tweet[:280]

