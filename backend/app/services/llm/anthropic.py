"""Anthropic provider adapter — Claude models over the Messages API.

Constructed with explicit credentials; reads no globals.
"""
from typing import AsyncGenerator, Dict, List


def prepare_anthropic_payload(messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, str]]]:
    """Split OpenAI-style messages into an Anthropic system prompt + conversation.

    Merges adjacent same-role turns, since the Messages API rejects them.
    """
    systems = []
    convo = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            systems.append(content)
        elif role in ("user", "assistant"):
            if convo and convo[-1]["role"] == role:
                convo[-1]["content"] += "\n\n" + content
            else:
                convo.append({"role": role, "content": content})
    if not convo:
        convo = [{"role": "user", "content": "Hello"}]
    return "\n\n".join(systems), convo


class AnthropicAdapter:
    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    @property
    def identity(self) -> tuple[str, str]:
        return "anthropic", self._model

    def describe(self) -> dict:
        return {}

    async def check_available(self) -> tuple[bool, str | None]:
        ok = bool(self._api_key)
        return ok, None if ok else "ANTHROPIC_API_KEY not configured (selected provider is anthropic)"

    async def stream_tokens(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        from anthropic import AsyncAnthropic

        system_prompt, convo = prepare_anthropic_payload(messages)
        client = AsyncAnthropic(api_key=self._api_key, base_url=self._base_url)
        async with client.messages.stream(
            model=self._model,
            system=system_prompt if system_prompt else None,
            messages=convo,
            temperature=0.2,
            max_tokens=4096,
        ) as s:
            async for text in s.text_stream:
                if text:
                    yield text
