"""Debug DeepSeek 400: test model name."""
import httpx, os, sys

key = os.popen("security find-generic-password -s DEEPSEEK_API_KEY -w").read().strip()
client = httpx.Client()

# Test 1: gpt-4o (current config — expected to fail)
r1 = client.post(
    "https://api.deepseek.com/v1/chat/completions",
    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    headers={"Authorization": f"Bearer {key}"},
    timeout=10,
)
print(f"Test 1 (model=gpt-4o): {r1.status_code}")
if r1.status_code != 200:
    print(f"  Body: {r1.text[:300]}")

# Test 2: deepseek-chat (correct model)
r2 = client.post(
    "https://api.deepseek.com/v1/chat/completions",
    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]},
    headers={"Authorization": f"Bearer {key}"},
    timeout=10,
)
print(f"Test 2 (model=deepseek-chat): {r2.status_code}")
if r2.status_code != 200:
    print(f"  Body: {r2.text[:300]}")
else:
    print(f"  Response: {r2.json()['choices'][0]['message']['content'][:100]}")

# Test 3: deepseek (without -chat suffix)
r3 = client.post(
    "https://api.deepseek.com/v1/chat/completions",
    json={"model": "deepseek", "messages": [{"role": "user", "content": "hi"}]},
    headers={"Authorization": f"Bearer {key}"},
    timeout=10,
)
print(f"Test 3 (model=deepseek): {r3.status_code}")
if r3.status_code != 200:
    print(f"  Body: {r3.text[:200]}")
