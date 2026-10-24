import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

key = os.getenv("XAI_API_KEY", "").strip()
base = os.getenv("XAI_BASE_URL", "https://api.reto.pltk.mx/v1").strip().rstrip("/")
model = os.getenv("GROK_MODEL", "grok-2-mini").strip()

print(f"base_url : {base}")
print(f"model    : {model}")
print(f"key len  : {len(key)}")
print(f"key pref : {key[:6]}..." if key else "NO KEY")

if not key:
    raise SystemExit("XAI_API_KEY vacía")

client = OpenAI(api_key=key, base_url=base)

# 1) listar modelos si el gateway lo soporta
try:
    models = client.models.list()
    ids = [m.id for m in models.data]
    print("Modelos disponibles (primeros 30):")
    for mid in ids[:30]:
        print(" -", mid)
except Exception as e:
    print("No se pudo listar modelos (normal en algunos gateways):", e)

# 2) chat de prueba
resp = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Responde solo: OK"}],
    max_tokens=16,
    temperature=0,
)
print("SUCCESS:", resp.choices[0].message.content)
print("Model used:", getattr(resp, "model", model))