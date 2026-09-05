"""A stand-in for OpenRouter, so the end-to-end suite never touches the network.

The brain service reaches the LLM over HTTP from its own process, so it cannot be monkeypatched
from the test runner — `OPENROUTER_BASE_URL` (see brain/openrouter.py) points it here instead.
Replies are deterministic and echo the question, which is what lets the chat spec assert on the
answer text.

    uv run python -m e2e.support.fake_openrouter --port 8099
"""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Fake OpenRouter")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = ""
    messages: list[Message] = []


# The chat spec asserts this marker appears in the assistant's reply.
ANSWER_PREFIX = "STUBBED ANSWER:"


@app.post("/chat/completions")
def chat_completions(body: ChatRequest) -> dict[str, object]:
    prompt = body.messages[-1].content if body.messages else ""
    # The mail-ask prompt ends with the user's question; echo a bounded slice of it so the
    # browser test can prove the round-trip carried real content.
    tail = prompt.strip().splitlines()[-1][:120] if prompt.strip() else ""
    return {
        "choices": [{"message": {"role": "assistant", "content": f"{ANSWER_PREFIX} {tail}"}}],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
