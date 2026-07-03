"""
Provider-agnostic LLM client. Returns a callable that takes a system prompt and
user message, and returns the model's text response.

Configured via environment / ROS params:
  LLM_PROVIDER  : 'anthropic', 'openai', 'xai', or 'ollama'
  LLM_API_KEY   : API key (not needed for ollama)
  LLM_MODEL     : model name (e.g. claude-opus-4-8, gpt-4o, grok-4.3, qwen2.5:3b)
  OLLAMA_HOST   : ollama server URL (default http://localhost:11434)
  LLM_BASE_URL  : override the OpenAI-compatible endpoint (openai/xai)
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
    """OpenAI-compatible client. Works with OpenAI and any compatible API
    (e.g. xAI Grok) via the base_url override."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url or None)
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


class OllamaClient:
    """Local LLM via Ollama. No API key required. Expects model to support JSON."""

    def __init__(self, model: str, host: str):
        import ollama
        self._client = ollama.Client(host=host)
        self._model = model

    def complete(self, system_prompt: str, user_message: str) -> str:
        resp = self._client.chat(
            model=self._model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message},
            ],
            format='json',
            options={'temperature': 0.2},
        )
        return resp['message']['content']


def get_client(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """Factory: build an LLM client from explicit args or environment variables."""
    provider = (provider or os.environ.get('LLM_PROVIDER', 'ollama')).lower()
    api_key = api_key or os.environ.get('LLM_API_KEY', '')
    model = model or os.environ.get('LLM_MODEL', '')

    if provider == 'ollama':
        host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        return OllamaClient(model or 'qwen2.5:3b', host)

    if not api_key:
        raise ValueError(f'LLM_API_KEY not set, required for provider {provider!r}')

    base_url = os.environ.get('LLM_BASE_URL', '') or None

    if provider == 'anthropic':
        return AnthropicClient(api_key, model or 'claude-opus-4-8')
    if provider == 'openai':
        return OpenAIClient(api_key, model or 'gpt-4o', base_url)
    if provider == 'xai':
        # xAI Grok exposes an OpenAI-compatible API
        return OpenAIClient(api_key, model or 'grok-4.3',
                            base_url or 'https://api.x.ai/v1')
    raise ValueError(
        f'Unknown LLM_PROVIDER: {provider!r} '
        '(expected ollama, anthropic, openai, or xai)')
