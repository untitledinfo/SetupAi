"""Example: python examples/python-sdk/example_usage.py"""

import os

from firewing_sdk import FirewingClient

client = FirewingClient(
    base_url=os.environ.get("FIREWING_BASE_URL", "http://localhost:8000"),
    api_key=os.environ["FIREWING_API_KEY"],
)

print(client.health())

reply = client.chat([{"role": "user", "content": "Say hello in five words."}])
print("Reply:", reply)

print("Streaming:")
for chunk in client.chat_stream([{"role": "user", "content": "Count to five."}]):
    print(chunk, end="", flush=True)
print()
