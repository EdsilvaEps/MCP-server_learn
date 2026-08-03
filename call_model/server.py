# -*- coding: utf-8 -*-
"""Lehmus AI MCP server

This server exposes a set of FastMCP tools that wrap the ConfidentialMind
Lehmus AI model endpoint.  The implementation follows the official
quick‑start instructions from
https://github.com/ConfidentialMind/confidentialmind-endpoints-quickstart/tree/main/model-endpoint
so that environment variables, request headers and URL handling match the
expected OpenAI‑compatible API.

Key differences from the previous version:

* Environment variable names are now ``BASE_URL``, ``API_KEY`` and ``MODEL_NAME``
  (no hidden defaults).  Missing ``API_KEY`` raises a clear error.
* ``Accept: application/json`` is always sent – the Lehmus API may reject
  requests lacking this header.
* ``httpx`` is forced to use HTTP/1.1 (``http2=False``) to avoid any subtle
  HTTP/2 negotiation issues that previously resulted in a 403.
* Helper ``build_url`` normalises slashes robustly.
* All tool functions use explicit arguments – no ``**kwargs`` – to satisfy the
  user’s preference for explicit signatures.
"""

import os
import json
from typing import Any, List, Dict, Optional

import httpx
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration – read from the environment exactly as the quick‑start repo
# expects.  No placeholder values are provided; the user must set them.
# ---------------------------------------------------------------------------
BASE_URL: str = os.getenv("BASE_URL", "https://api.lehmus-ai.oulu.fi")
API_KEY: Optional[str] = os.getenv("API_KEY")
MODEL_NAME: str = os.getenv("MODEL_NAME", "jwwqblcgkizlhxjjbkcp")
HOST: str = os.getenv("HOST", "127.0.0.1")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", os.getenv("PORT", "4000")))
MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "stdio").lower()
TIMEOUT_SECONDS: float = float(os.getenv("LEHMUS_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# HTTP request preparation – always include JSON content type and explicit
# Accept header.  Authorization is added only when a key is present; otherwise
# we raise an informative error.
# ---------------------------------------------------------------------------
HEADERS: Dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"
else:
    raise RuntimeError(
        "Lehmus AI API key not found. Set the environment variable 'API_KEY' "
        "to your ConfidentialMind API key."
    )

# ---------------------------------------------------------------------------
# FastMCP server definition
# ---------------------------------------------------------------------------
server = FastMCP(
    name="lehmus-ai-gemma-mcp",
    instructions=(
        "FastMCP server exposing OpenAI‑compatible tools for the ConfidentialMind "
        "Lehmus AI model endpoint."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def build_url(path: str) -> str:
    """Join ``BASE_URL`` and ``path`` ensuring exactly one ``/`` separator.

    The quick‑start examples use paths like ``/v1/models``; ``BASE_URL`` may or
    may not end with a slash.  This helper guarantees the final URL is correct.
    """
    base = BASE_URL.rstrip("/")
    clean_path = path.lstrip("/")
    return f"{base}/{clean_path}"


def call_provider(
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    method: str = "POST",
) -> Any:
    """Perform a request against the Lehmus AI endpoint.

    ``payload`` is JSON‑encoded when supplied.  ``method`` can be ``GET`` for
    model listing or ``POST`` for chat / completion calls.
    """
    request_kwargs: Dict[str, Any] = {
        "headers": HEADERS,
        "timeout": TIMEOUT_SECONDS,
    }
    if payload is not None:
        request_kwargs["json"] = payload

    # ``http2=False`` mirrors the behaviour that succeeded with ``curl``.
    with httpx.Client(http2=False) as client:
        response = client.request(method, build_url(path), **request_kwargs)
        # ``raise_for_status`` will raise an httpx.HTTPStatusError for non‑2xx.
        response.raise_for_status()
        return response.json()

# ---------------------------------------------------------------------------
# Tool implementations – explicit signatures as requested by the user.
# ---------------------------------------------------------------------------
def _run_chat_completion(
    tool_name: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not messages:
        raise ValueError("'messages' must be a non‑empty list of dicts.")
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stop": stop,
    }
    return {
        "tool": tool_name,
        "model": MODEL_NAME,
        "request": payload,
        "response": call_provider("v1/chat/completions", payload),
    }


def _run_text_completion(
    tool_name: str,
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not prompt:
        raise ValueError("'prompt' must be a non‑empty string.")
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stop": stop,
    }
    return {
        "tool": tool_name,
        "model": MODEL_NAME,
        "request": payload,
        "response": call_provider("v1/completions", payload),
    }

# ---------------------------------------------------------------------------
# FastMCP tool decorations – these are the public endpoints used by the client.
# ---------------------------------------------------------------------------
@server.tool(name="chatgpt_chat_completion", description="Run an OpenAI‑compatible chat completion against Lehmus AI.")
def chatgpt_chat_completion(
    messages: List[Dict[str, str]],
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return _run_chat_completion(
        "chatgpt_chat_completion",
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
    )

@server.tool(name="chatgpt_text_completion", description="Run an OpenAI‑compatible text completion against Lehmus AI.")
def chatgpt_text_completion(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return _run_text_completion(
        "chatgpt_text_completion",
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
    )

@server.tool(name="gemma_chat_completion", description="Run a chat completion using the Gemma model via Lehmus AI.")
def gemma_chat_completion(
    messages: List[Dict[str, str]],
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return _run_chat_completion(
        "gemma_chat_completion",
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
    )

@server.tool(name="gemma_text_completion", description="Run a text completion using the Gemma model via Lehmus AI.")
def gemma_text_completion(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return _run_text_completion(
        "gemma_text_completion",
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
    )

@server.tool(name="lehmus_health", description="Check Lehmus AI availability and list supported models.")
def lehmus_health() -> Dict[str, Any]:
    """Return a health payload.

    ``available`` is ``True`` when the ``GET /v1/models`` request succeeds.
    On failure we capture the exception text for diagnostics.
    """
    try:
        models = call_provider("v1/models", None, method="GET")
        return {
            "available": True,
            "api_url": BASE_URL,
            "default_model": MODEL_NAME,
            "models": models,
        }
    except httpx.HTTPError as exc:
        return {
            "available": False,
            "api_url": BASE_URL,
            "default_model": MODEL_NAME,
            "error": str(exc),
        }

# Alias kept for backward compatibility – the quick‑start calls it a compatibility shim.
@server.tool(name="gemma_health", description="Compatibility alias for Lehmus AI health checks.")
def gemma_health() -> Dict[str, Any]:
    return lehmus_health()

# ---------------------------------------------------------------------------
# Entry‑point – honour the transport choice (stdio vs http).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if MCP_TRANSPORT == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=HOST, port=SERVER_PORT)
