"""
Provider-agnostic LLM client. Returns a callable that takes a system prompt and
user message, and returns the model's text response.

Configured via environment / ROS params:
  LLM_PROVIDER  — 'anthropic' or 'openai'
  LLM_API_KEY   — API key for the chosen provider
  LLM_MODEL     — model name (e.g. claude-sonnet-4-6, gpt-4o)
"""

from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str:
        """Return the model's text response as a string (expected to be JSON)."""
        ...


class AnthropicClient:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_message: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=[{
                'type': 'text',
                'text': system_prompt,
                'cache_control': {'type': 'ephemeral'},
            }],
            messages=[{'role': 'user', 'content': user_message}],
        )
        return resp.content[0].text


class OpenAIClient:
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_message: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message},
            ],
            response_format={'type': 'json_object'},
            temperature=0.2,
        )
        return resp.choices[0].message.content


def get_client(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """Factory: build an LLM client from explicit args or environment variables."""
    provider = (provider or os.environ.get('LLM_PROVIDER', 'anthropic')).lower()
    api_key = api_key or os.environ.get('LLM_API_KEY', '')
    model = model or os.environ.get('LLM_MODEL', '')

    if not api_key:
        raise ValueError('LLM_API_KEY not set — cannot create LLM client')

    if provider == 'anthropic':
        return AnthropicClient(api_key, model or 'claude-sonnet-4-6')
    if provider == 'openai':
        return OpenAIClient(api_key, model or 'gpt-4o')
    raise ValueError(f'Unknown LLM_PROVIDER: {provider!r} (expected anthropic or openai)')
