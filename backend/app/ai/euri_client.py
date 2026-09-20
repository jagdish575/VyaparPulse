"""EURI client. All EURI-specific code lives in app/ai/.

Per the EURI docs the API is OpenAI-compatible:
    POST {EURI_BASE_URL}/chat/completions      (default base: https://api.euron.one/api/v1/euri)
    Authorization: Bearer <EURI_API_KEY>
    body: {"model", "messages", "temperature", "max_tokens"}
Native function-calling / JSON-mode are not documented for EURI, so we do NOT send those parameters.
Structured output is enforced by prompting for JSON and strictly validating it with Pydantic;
tool selection is validated against a backend allow-list. The API key never leaves the backend.
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings

log = logging.getLogger("kirai.euri")
T = TypeVar("T", bound=BaseModel)
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="euri")


class EuriError(Exception):
    """Raised for any EURI failure. Messages never contain the API key."""


class EuriTimeout(EuriError):
    """EURI did not answer within the configured time budget (never retried: the demo must not stall)."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model output")
    return json.loads(text[start : end + 1])


class EuriClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.api_key = settings.EURI_API_KEY if api_key is None else api_key
        self.base_url = (base_url or settings.EURI_BASE_URL).rstrip("/")
        self.model = model or settings.EURI_MODEL
        self.timeout = timeout or settings.EURI_TIMEOUT_SECONDS

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ core call
    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 700) -> str:
        if not self.configured:
            raise EuriError("EURI_API_KEY is not configured")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # httpx timeouts apply per socket operation, not to the whole call. A slow gateway could therefore
        # stall a request far beyond `timeout`, so enforce a hard wall-clock deadline in a worker thread.
        future = _POOL.submit(
            httpx.post, f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=self.timeout
        )
        try:
            resp = future.result(timeout=self.timeout)
        except FutureTimeout:
            future.cancel()
            raise EuriTimeout(f"EURI did not respond within {self.timeout:g}s") from None
        except httpx.TimeoutException:
            raise EuriTimeout(f"EURI did not respond within {self.timeout:g}s") from None
        except httpx.HTTPError as exc:
            raise EuriError(f"EURI request failed ({type(exc).__name__})") from None
        if resp.status_code >= 400:
            log.warning("EURI HTTP %s: %s", resp.status_code, resp.text[:300])
            raise EuriError(f"EURI returned HTTP {resp.status_code}")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise EuriError("EURI returned an unexpected response shape") from None
        if isinstance(content, list):  # docs: content may be an array of text objects
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        if not isinstance(content, str) or not content.strip():
            raise EuriError("EURI returned an empty response")
        return content

    # ------------------------------------------------------------------ structured output
    def structured_output(self, messages: list[dict], schema: type[T], schema_hint: str | None = None) -> T:
        """Ask for JSON, validate it against `schema`, and retry once with the validation error."""
        hint = schema_hint or json.dumps(schema.model_json_schema())
        msgs = list(messages) + [
            {"role": "system", "content": f"Respond with ONLY a single JSON object matching this schema:\n{hint}"}
        ]
        last_error: Exception | None = None
        for _ in range(2):
            raw = self.chat(msgs, temperature=0.0, max_tokens=400)
            try:
                return schema.model_validate(_extract_json(raw))
            except (ValueError, ValidationError) as exc:
                last_error = exc
                msgs = msgs + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That was not valid ({str(exc)[:200]}). Return ONLY the corrected JSON object."},
                ]
        raise EuriError(f"model did not return valid structured output: {str(last_error)[:120]}")

    # ------------------------------------------------------------------ tool selection
    def tool_call(self, messages: list[dict], tools: list[dict]) -> tuple[str, dict] | None:
        """Let the model pick ONE tool from an allow-list. Returns (tool_name, arguments) or None.
        The selection is validated here; the backend (not the model) executes the tool."""
        allowed = {t["name"] for t in tools}
        catalogue = "\n".join(f"- {t['name']}: {t['description']} args={json.dumps(t.get('parameters', {}))}" for t in tools)
        msgs = list(messages) + [
            {
                "role": "system",
                "content": "Pick exactly one tool or none. Reply ONLY with JSON: "
                '{"tool": "<name or null>", "arguments": {...}}\nAvailable tools:\n' + catalogue,
            }
        ]
        data = _extract_json(self.chat(msgs, temperature=0.0, max_tokens=300))
        name = data.get("tool")
        args = data.get("arguments")
        if name not in allowed or not isinstance(args, dict):
            return None
        return name, args

    # ------------------------------------------------------------------ health
    def ping(self) -> tuple[bool, str | None]:
        if not self.configured:
            return False, "EURI_API_KEY is not set"
        try:
            self.chat([{"role": "user", "content": "Reply with the single word: ok"}], temperature=0, max_tokens=5)
            return True, None
        except EuriError as exc:
            return False, str(exc)
