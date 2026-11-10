"""Prompt construction, message translation, and tool-call parsing for Antigravity."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any, Sequence

_ROLE_LABELS = {
    "system": "System",
    "user": "User",
    "assistant": "Assistant",
    "tool": "Tool Result",
}

_PROMPT_PREAMBLE = (
    "You are being used strictly as an LLM inference backend for Hermes Agent.",
    "You do not possess any local execution tools in this mode. You MUST NOT attempt to invoke native agent tools (such as run_command, write_to_file, view_file, etc.).",
    "All tool executions and filesystem interactions are performed exclusively by Hermes Agent.",
    "IMPORTANT INSTRUCTIONS FOR TOOLS:",
    "- If you need to call a tool, emit ONLY <tool_call>{...}</tool_call> blocks in your text output.",
    "- Each tool call must be a JSON object containing 'id', 'type': 'function', and 'function': {'name': '...', 'arguments': '...'}.",
    "- 'arguments' must be a JSON-encoded string containing the function arguments.",
    "- Do NOT execute local shell commands or file operations directly; only output <tool_call> tags so Hermes can execute them safely.",
    "- NEVER simulate or hallucinate Tool Results (e.g. 'Tool Result (...):'). Hermes Agent executes tools externally and will supply real results in subsequent turns.",
    "- After emitting tool calls, STOP generating immediately. Do NOT generate results, execution output, or commentary after tool calls.",
    "- If no tool is needed, respond naturally with standard text.",
)

_TOOL_CALL_PREFIXES = tuple(
    "<tool_call>"[:i] for i in range(len("<tool_call>"), 0, -1)
)


def _render_image_item(item: dict[str, Any]) -> str:
    """Extract local image path or cache data URI / URL for agy image reference."""
    url = ""
    img_val = item.get("image_url")
    if isinstance(img_val, dict):
        url = str(img_val.get("url") or "")
    elif isinstance(img_val, str):
        url = img_val
    elif "image" in item:
        url = str(item.get("image") or "")
    elif "url" in item:
        url = str(item.get("url") or "")

    url = url.strip()
    if not url:
        return ""

    if url.startswith("file://"):
        url = url[7:]

    if url.startswith("data:image/") and ";base64," in url:
        try:
            import base64
            import hashlib
            from pathlib import Path

            header, b64_data = url.split(";base64,", 1)
            ext = "png"
            if "image/" in header:
                mime_sub = header.split("image/", 1)[1].split(";", 1)[0]
                if mime_sub in ("jpeg", "jpg"):
                    ext = "jpg"
                elif mime_sub in ("gif", "webp"):
                    ext = mime_sub
            img_bytes = base64.b64decode(b64_data)
            h = hashlib.sha256(img_bytes).hexdigest()[:16]
            cache_dir = Path("/tmp/hermes_images")
            cache_dir.mkdir(parents=True, exist_ok=True)
            img_file = cache_dir / f"img_{h}.{ext}"
            if not img_file.exists():
                img_file.write_bytes(img_bytes)
            url = str(img_file)
        except Exception:
            pass
    elif url.startswith(("http://", "https://")):
        try:
            import hashlib
            import urllib.request
            from pathlib import Path

            h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            raw_path = url.split("?")[0]
            ext = raw_path.split(".")[-1].lower() if "." in raw_path else "png"
            if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
                ext = "png"
            cache_dir = Path("/tmp/hermes_images")
            cache_dir.mkdir(parents=True, exist_ok=True)
            img_file = cache_dir / f"web_{h}.{ext}"
            if not img_file.exists():
                req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    img_file.write_bytes(resp.read())
            url = str(img_file)
        except Exception:
            pass

    return f"[Attached image: @{url}] (Inspect the image visual pixels directly without calling file inspection tools)"



def _render_file_item(item: dict[str, Any]) -> str:
    """Extract document/file path or cache data URI / URL for agy file reference."""
    url = ""
    for k in ("file_path", "path", "file_url", "url", "file", "document"):
        if k in item and item[k]:
            v = item[k]
            if isinstance(v, dict) and "url" in v:
                url = str(v["url"] or "")
            elif isinstance(v, str):
                url = v
            if url:
                break
    url = url.strip()
    if not url:
        return ""
    if url.startswith("file://"):
        url = url[7:]
    from pathlib import Path
    try:
        p = Path(url)
        if p.exists() and p.is_file():
            return f"[Attached file: @{url}]"
    except Exception:
        pass
    if url.startswith("data:") and ";base64," in url:
        try:
            import base64
            import hashlib
            header, b64_data = url.split(";base64,", 1)
            ext = "bin"
            if "/" in header:
                mime_sub = header.split("/", 1)[1].split(";", 1)[0]
                if mime_sub in ("pdf", "txt", "csv", "json", "md", "html"):
                    ext = mime_sub
            doc_bytes = base64.b64decode(b64_data)
            h = hashlib.sha256(doc_bytes).hexdigest()[:16]
            cache_dir = Path("/tmp/hermes_docs")
            cache_dir.mkdir(parents=True, exist_ok=True)
            doc_file = cache_dir / f"doc_{h}.{ext}"
            if not doc_file.exists():
                doc_file.write_bytes(doc_bytes)
            return f"[Attached file: @{doc_file}]"
        except Exception:
            pass
    elif url.startswith(("http://", "https://")):
        try:
            import hashlib
            import urllib.request
            h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            raw_path = url.split("?")[0]
            ext = raw_path.split(".")[-1].lower() if "." in raw_path else "pdf"
            cache_dir = Path("/tmp/hermes_docs")
            cache_dir.mkdir(parents=True, exist_ok=True)
            doc_file = cache_dir / f"doc_{h}.{ext}"
            if not doc_file.exists():
                req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    doc_file.write_bytes(resp.read())
            return f"[Attached file: @{doc_file}]"
        except Exception:
            pass
    return f"[Attached file: @{url}]"


def _render_message_content(content: Any) -> str:
    """Normalize multimodal or structured message content into a string."""
    if content is None:
        return ""
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "").strip()
        return str(content.get("content") or "").strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item.strip())
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or "").strip())
                elif item.get("type") in ("image_url", "image") or "image_url" in item:
                    img_tag = _render_image_item(item)
                    if img_tag:
                        parts.append(img_tag)
                elif item.get("type") in ("document", "file", "attachment") or any(k in item for k in ("file_path", "file_url", "document")):
                    doc_tag = _render_file_item(item)
                    if doc_tag:
                        parts.append(doc_tag)
                elif "content" in item:
                    parts.append(str(item.get("content") or "").strip())
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def _format_messages_as_prompt(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any = None,
    rules_in_workspace: bool = False,
) -> str:
    """Assemble Hermes message history, system prompt, and tool schemas into a canonical prompt.

    ``rules_in_workspace``: the preamble and system prompt already live in the workspace GEMINI.md
    (see ``soul.py``), so the stdin turn carries only tools and conversation.
    """
    try:
        from agent.acp_openai_bridge import render_tool_bridge_sections
        tool_sections = render_tool_bridge_sections(tools, tool_choice)
    except Exception:
        tool_sections = []
        if tools:
            tool_sections.append(
                "Available tools (OpenAI function schema):\n"
                + json.dumps(tools, ensure_ascii=False)
            )

    sections: list[str] = [*([] if rules_in_workspace else _PROMPT_PREAMBLE), *tool_sections]

    valid_messages = [m for m in messages if isinstance(m, dict)]
    last_msg = valid_messages[-1] if valid_messages else None
    last_role = str(last_msg.get("role") or "").strip().lower() if last_msg else ""

    system_parts: list[str] = []
    history_messages: list[dict[str, Any]] = []

    for msg in valid_messages:
        role = str(msg.get("role") or "unknown").strip().lower()
        if role == "system":
            rendered = _render_message_content(msg.get("content"))
            if rendered:
                system_parts.append(rendered)
        else:
            history_messages.append(msg)

    if system_parts and not rules_in_workspace:
        sections.append("### SYSTEM INSTRUCTIONS (HERMES AGENT):\n" + "\n\n".join(f"System:\n{p}" for p in system_parts))

    _HISTORICAL_TOOL_RETENTION_COUNT = 8
    _HISTORICAL_TOOL_MAX_CHARS = 300
    _TOOL_MAX_CHARS_CAP = 20000

    transcript: list[str] = []
    prior_messages = history_messages[:-1] if last_role == "user" and len(history_messages) > 1 else history_messages

    tool_indices = [
        i for i, msg in enumerate(prior_messages)
        if str(msg.get("role") or "").strip().lower() == "tool"
    ]
    recent_tool_cutoff = (
        set(tool_indices[-_HISTORICAL_TOOL_RETENTION_COUNT:])
        if len(tool_indices) > _HISTORICAL_TOOL_RETENTION_COUNT
        else set(tool_indices)
    )

    for i, message in enumerate(prior_messages):
        role = str(message.get("role") or "unknown").strip().lower()
        rendered_content = _render_message_content(message.get("content"))

        if role == "tool":
            tool_id = str(message.get("tool_call_id") or message.get("name") or "tool").strip()
            if i not in recent_tool_cutoff and len(rendered_content) > _HISTORICAL_TOOL_MAX_CHARS:
                rendered_content = (
                    rendered_content[:200]
                    + f"\n[... tool output truncated: {len(rendered_content)} chars ...]\n"
                    + rendered_content[-100:]
                )
            elif len(rendered_content) > _TOOL_MAX_CHARS_CAP:
                rendered_content = (
                    rendered_content[:12000]
                    + f"\n[... large tool output truncated: {len(rendered_content)} chars ...]\n"
                    + rendered_content[-3000:]
                )
            transcript.append(f"Tool Result ({tool_id}):\n{rendered_content}")
            continue

        if role == "assistant":
            parts = []
            if "Tool Result (" in rendered_content:
                rendered_content = rendered_content.split("Tool Result (")[0].strip()
            if tool_calls := message.get("tool_calls"):
                # Strip any raw <tool_call> blocks from rendered content to avoid duplicate emission
                rendered_content = re.sub(r"<tool_call>.*?<\/tool_call>", "", rendered_content, flags=re.DOTALL).strip()
            if rendered_content:
                parts.append(rendered_content)
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        fn = tc.get("function") or {}
                        call_obj = {
                            "id": tc.get("id") or "call_1",
                            "type": "function",
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", "{}") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments", {}), ensure_ascii=False)
                            }
                        }
                        parts.append(f"<tool_call>{json.dumps(call_obj, ensure_ascii=False)}</tool_call>")
            if parts:
                transcript.append("Assistant:\n" + "\n".join(parts))
            continue

        label = _ROLE_LABELS.get(role, "Context")
        if rendered_content:
            transcript.append(f"{label}:\n{rendered_content}")

    if transcript:
        sections.append("Conversation transcript:\n\n" + "\n\n".join(transcript))

    if last_role == "tool":
        sections.append(
            "### LATEST TOOL RESULTS RECEIVED.\n"
            "INSTRUCTION: Evaluate the latest tool results in the transcript above and continue the task. "
            "If more tools are needed, emit <tool_call> tags. If you have enough information, "
            "respond clearly to the user without repeating prior summaries."
        )
    elif last_role == "user" and last_msg is not None:
        user_text = _render_message_content(last_msg.get("content"))
        sections.append(
            f"### LATEST USER REQUEST TO ANSWER:\nUser:\n{user_text}\n\n"
            "INSTRUCTION: Respond directly and specifically to the LATEST USER REQUEST above. "
            "Do NOT repeat previous architectural summaries, code reviews, or overview boilerplate unless explicitly asked."
        )
    else:
        sections.append("Continue the conversation from the latest message.")
    return "\n\n".join(s.strip() for s in sections if s and s.strip())


def _messages_match_prefix(history: Sequence[dict[str, Any]], incoming: Sequence[dict[str, Any]]) -> bool:
    """Return True if incoming messages strictly extend history as a continuation."""
    if not history or len(incoming) <= len(history):
        return False
    for i, h_msg in enumerate(history):
        inc_msg = incoming[i]
        if not isinstance(inc_msg, dict) or not isinstance(h_msg, dict):
            return False
        if inc_msg.get("role") != h_msg.get("role"):
            return False
        if inc_msg.get("content") != h_msg.get("content"):
            return False
        if inc_msg.get("tool_calls") != h_msg.get("tool_calls"):
            return False
    return True


def _format_delta_prompt(new_messages: Sequence[dict[str, Any]]) -> str:
    """Format only the incremental messages in an ongoing multi-turn interaction."""
    parts: list[str] = []
    last_role = ""
    for msg in new_messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        last_role = role
        rendered_content = _render_message_content(msg.get("content"))
        if role == "tool":
            tool_id = str(msg.get("tool_call_id") or msg.get("name") or "tool").strip()
            if len(rendered_content) > 20000:
                rendered_content = (
                    rendered_content[:12000]
                    + f"\n[... large tool output truncated: {len(rendered_content)} chars ...]\n"
                    + rendered_content[-3000:]
                )
            parts.append(f"Tool Result ({tool_id}):\n{rendered_content}")
            continue
        if role == "assistant":
            subparts = []
            if "Tool Result (" in rendered_content:
                rendered_content = rendered_content.split("Tool Result (")[0].strip()
            if tool_calls := msg.get("tool_calls"):
                rendered_content = re.sub(r"<tool_call>.*?<\/tool_call>", "", rendered_content, flags=re.DOTALL).strip()
            if rendered_content:
                subparts.append(rendered_content)
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        fn = tc.get("function") or {}
                        call_obj = {
                            "id": tc.get("id") or "call_1",
                            "type": "function",
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", "{}") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments", {}), ensure_ascii=False)
                            }
                        }
                        subparts.append(f"<tool_call>{json.dumps(call_obj, ensure_ascii=False)}</tool_call>")
            if subparts:
                parts.append("Assistant:\n" + "\n".join(subparts))
            continue
        label = _ROLE_LABELS.get(role, "Context")
        if rendered_content:
            parts.append(f"{label}:\n{rendered_content}")

    if last_role == "tool":
        parts.append(
            "Continue the conversation from the latest tool result. "
            "Evaluate the latest tool result above and continue the task. "
            "If more tools are needed, emit <tool_call> tags. "
            "If you have enough information to fulfill the user's request, provide your clear response. "
            "Do NOT return an empty response."
        )
    elif last_role == "user":
        parts.append(
            "Respond directly and specifically to the latest user request above. "
            "Do NOT repeat previous architectural summaries or boilerplate."
        )
    else:
        parts.append("Continue the conversation from the latest message above.")
    return "\n\n".join(s.strip() for s in parts if s and s.strip())


def _longest_tool_call_prefix_match(text: str) -> int:
    """Return the length of the longest suffix of `text` that matches a prefix of `<tool_call>`."""
    for prefix in _TOOL_CALL_PREFIXES:
        if text.endswith(prefix):
            return len(prefix)
    return 0


def _parse_tool_block(block: str) -> tuple[list[Any], str]:
    """Parse tool call blocks, returning (tool_call_deltas, cleaned_text)."""
    calls = []
    cleaned_text = ""
    try:
        from agent.acp_openai_bridge import extract_tool_calls_from_text
        calls, cleaned_text = extract_tool_calls_from_text(block)
    except Exception:
        m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", block, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(1))
                fn = obj.get("function", {})
                call_id = obj.get("id") or "call_1"
                fn_name = fn.get("name", "")
                fn_args = fn.get("arguments", "{}")
                if not isinstance(fn_args, str):
                    fn_args = json.dumps(fn_args, ensure_ascii=False)
                calls = [
                    SimpleNamespace(
                        id=call_id,
                        type="function",
                        function=SimpleNamespace(name=fn_name, arguments=fn_args),
                    )
                ]
                cleaned_text = block[:m.start()] + block[m.end():]
            except Exception:
                cleaned_text = block
        else:
            cleaned_text = block

    deltas = []
    for i, call in enumerate(calls):
        fn = getattr(call, "function", None)
        name = getattr(fn, "name", "") if fn else ""
        args = getattr(fn, "arguments", "{}") if fn else "{}"
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        deltas.append(
            SimpleNamespace(
                index=i,
                id=getattr(call, "id", f"call_{i+1}"),
                type="function",
                function=SimpleNamespace(name=name, arguments=args),
            )
        )
    return deltas, cleaned_text.strip()
