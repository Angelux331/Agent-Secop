import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

key = os.getenv("XAI_API_KEY", "").strip()
model = os.getenv("GROK_MODEL", "grok-2-mini")

print(f"Key length: {len(key)}")
print(f"Key prefix: {key[:6]}..." if key else "NO KEY")
print(f"Model: {model}")

if not key:
    raise SystemExit("XAI_API_KEY vacía. Revisa el archivo .env")

client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")

resp = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Responde solo: OK"}],
    max_tokens=16,
    temperature=0,
)
print("SUCCESS:", resp.choices[0].message.content)
print("Model used:", resp.model)