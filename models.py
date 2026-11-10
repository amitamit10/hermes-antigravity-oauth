"""Exact native model IDs and optional CLI effort flags for Antigravity."""

from __future__ import annotations

# Compatibility exports used by client.py; neither invents account models.
_FALLBACK_MODELS: tuple[str, ...] = ()
_MODEL_ALIASES: dict[str, str] = {}

# Official agy --effort vocabulary, not a model availability table.
_CLI_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def model_effort(model: str | None) -> str | None:
    """Recognize a native effort suffix without changing the inference ID."""
    suffix = (model or "").rpartition("-")[2]
    return suffix if suffix in _CLI_EFFORTS else None


def supports_effort_flag(model: str | None) -> bool:
    """Only manual suffixless Gemini requests accept the separate CLI flag."""
    return bool(model and model.startswith("gemini-") and not model_effort(model))


def _normalize_effort(effort: str | None) -> str | None:
    if not effort:
        return None
    value = str(effort).strip().lower()
    if value in ("none", "off", "minimal"):
        return "low"
    return value if value in _CLI_EFFORTS else None


def resolve_model_and_effort(
    model: str | None,
    reasoning_effort: str | None = None,
) -> tuple[str, str | None]:
    """Pass selected IDs verbatim; native variants own their effort.

    Manual suffixless Gemini requests may use agy's --effort vocabulary.
    No generated IDs, aliases, inherited config or implicit model/effort defaults.
    An omitted model lets the official CLI choose its own default.
    """
    selected = model or ""
    effort = _normalize_effort(reasoning_effort) if supports_effort_flag(selected) else None
    return selected, effort
