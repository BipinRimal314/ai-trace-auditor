"""Sample Python app with AI SDK usage for testing."""

import anthropic
from openai import OpenAI
from fastapi import FastAPI

app = FastAPI()
client = anthropic.Anthropic()
openai_client = OpenAI()

MODEL = "claude-3-opus-20240229"
GPT_MODEL = "gpt-4o-2024-05-13"


@app.post("/api/chat")
async def chat(prompt: str):
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return {"response": response.content[0].text}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
