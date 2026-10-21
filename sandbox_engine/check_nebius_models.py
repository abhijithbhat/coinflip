import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NEBIUS_API_KEY"),
    base_url=os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
)

print("1. Fetching available NVIDIA / Nemotron models on Nebius Token Factory...")
models = client.models.list()
nemotron_models = [m.id for m in models.data if "nemotron" in m.id.lower() or "nvidia" in m.id.lower()]

for m_id in sorted(nemotron_models):
    print("  ->", m_id)

if nemotron_models:
    test_model = nemotron_models[0]
    print(f"\n2. Testing runtime call with: {test_model}")
    resp = client.chat.completions.create(
        model=test_model,
        messages=[{"role": "user", "content": "Say 'Token Factory Ready' in 3 words."}],
        max_tokens=256
    )
    msg = resp.choices[0].message
    print("Content:", msg.content)
    if hasattr(msg, "reasoning_content") and msg.reasoning_content:
        print("Reasoning field detected (length):", len(msg.reasoning_content))
