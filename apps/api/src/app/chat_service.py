from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from anthropic import Anthropic
from openai import OpenAI

from .core import (
    add_message,
    apply_canvas_tool,
    apply_edit_to_last_user,
    build_response_input,
    create_conversation,
    current_artifact_id_from_payload,
    get_conversation_or_404,
    get_session_factory,
    get_settings,
    json_dumps,
    prepare_regenerate,
    serialize_artifact,
    serialize_conversation,
    serialize_message,
)
from .models import MODEL_CATALOG, ModelSpec, get_model_spec
from .schemas import CanvasToolCall, ChatRequest, EditLastUserRequest, RegenerateRequest


SYSTEM_PROMPT = """You are Workpad AI, an expert assistant that collaborates through a split-pane workspace.

Rules:
- Keep chat responses concise, useful, and grounded in the user's request.
- Use the canvas_apply tool whenever the user asks you to draft, write, revise, structure, or transform durable content.
- Prefer markdown for prose and structured writing.
- Prefer python, typescript, javascript, html, json, or text for code and technical outputs.
- If a user wants to modify an existing artifact, prefer action=patch when the edit is targeted and replace when the artifact should be rewritten.
- Tool summaries should be short and concrete.
- Never emit raw JSON to the user unless they explicitly ask for it.
"""

ANTHROPIC_MAX_TOKENS = 8192


def sse_event(payload: dict[str, Any]) -> str:
    return f"event: app\ndata: {json_dumps(payload)}\n\n"


def chunk_text(value: str, chunk_size: int = 180) -> Iterator[str]:
    for index in range(0, len(value), chunk_size):
        yield value[index : index + chunk_size]


def _canvas_parameters_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "replace", "patch"],
                "description": "How the artifact should change.",
            },
            "title": {
                "type": "string",
                "description": "Human-readable title for the artifact.",
            },
            "content_type": {
                "type": "string",
                "enum": ["markdown", "python", "typescript", "javascript", "html", "json", "text"],
                "description": "The artifact language or format.",
            },
            "summary": {
                "type": "string",
                "description": "Short explanation of what changed.",
            },
            "content": {
                "type": ["string", "null"],
                "description": "Full artifact content for create or replace.",
            },
            "patches": {
                "type": ["array", "null"],
                "description": "Ordered search-and-replace patches for targeted edits.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "search": {"type": "string"},
                        "replace": {"type": "string"},
                        "replace_all": {"type": "boolean"},
                        "allow_missing": {"type": "boolean"},
                    },
                    "required": ["search", "replace", "replace_all", "allow_missing"],
                },
            },
        },
        "required": ["action", "title", "content_type", "summary", "content", "patches"],
    }


def _openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "canvas_apply",
            "description": "Create or update the persistent workpad artifact that appears beside chat.",
            "strict": True,
            "parameters": _canvas_parameters_schema(),
        }
    ]


def _anthropic_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "canvas_apply",
            "description": "Create or update the persistent workpad artifact that appears beside chat.",
            "input_schema": _canvas_parameters_schema(),
        }
    ]


def _artifact_context(payload: ChatRequest) -> str:
    if payload.current_artifact is None:
        return ""
    artifact = payload.current_artifact
    return (
        "\nThe user currently has an artifact open.\n"
        f"Title: {artifact.title}\n"
        f"Content type: {artifact.content_type.value}\n"
        f"Version: {artifact.version or 'unknown'}\n"
        "<artifact>\n"
        f"{artifact.content}\n"
        "</artifact>\n"
    )


def _as_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return item
    return dict(item)


@dataclass
class NormalizedToolCall:
    name: str
    arguments: str
    call_id: str


@dataclass
class StreamPassResult:
    text: str = ""
    tool_calls: list[NormalizedToolCall] = field(default_factory=list)
    openai_response_id: str | None = None
    anthropic_assistant_blocks: list[dict[str, Any]] | None = None


class WorkpadChatService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.session_factory = get_session_factory()
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None
        self.anthropic_client = Anthropic(api_key=self.settings.anthropic_api_key) if self.settings.anthropic_api_key else None

    def available_models(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for spec in MODEL_CATALOG:
            available = (spec.provider == "openai" and self.openai_client is not None) or (
                spec.provider == "anthropic" and self.anthropic_client is not None
            )
            entries.append({"id": spec.id, "label": spec.label, "provider": spec.provider, "available": available})
        return entries

    def _resolve_model(self, model_id: str | None) -> ModelSpec:
        spec = get_model_spec(model_id or self.settings.default_model)
        if spec.provider == "openai" and self.openai_client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        if spec.provider == "anthropic" and self.anthropic_client is None:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
        return spec

    def _stream_openai(
        self,
        spec: ModelSpec,
        payload: ChatRequest,
        input_items: list[dict[str, Any]],
        tool_choice: str | None = None,
        previous_response_id: str | None = None,
    ) -> tuple[Iterator[str], StreamPassResult]:
        assert self.openai_client is not None
        request_kwargs: dict[str, Any] = {
            "model": spec.api_name,
            "instructions": SYSTEM_PROMPT + _artifact_context(payload),
            "input": input_items,
            "tools": _openai_tools() if tool_choice != "none" else [],
            "parallel_tool_calls": False,
            "tool_choice": tool_choice,
            "previous_response_id": previous_response_id,
            "stream": True,
        }
        if spec.supports_reasoning:
            request_kwargs["reasoning"] = {"effort": self.settings.openai_reasoning_effort}

        stream = self.openai_client.responses.create(**request_kwargs)

        text_fragments: list[str] = []
        tool_calls: list[NormalizedToolCall] = []
        response_id: str | None = None
        emitted_started = False

        def iterator() -> Iterator[str]:
            nonlocal emitted_started, response_id
            for event in stream:
                event_type = getattr(event, "type", None)
                data = _as_dict(event)
                response = data.get("response")
                if isinstance(response, dict) and response.get("id"):
                    response_id = str(response["id"])
                if event_type == "response.output_text.delta":
                    if not emitted_started:
                        emitted_started = True
                        yield sse_event({"type": "assistant.message.started", "messageId": f"draft-{uuid4()}"})
                    delta = data.get("delta", "")
                    text_fragments.append(delta)
                    yield sse_event({"type": "assistant.message.delta", "delta": delta})
                elif event_type == "response.output_item.done":
                    item = data.get("item", {})
                    if item.get("type") == "function_call":
                        tool_calls.append(
                            NormalizedToolCall(
                                name=item.get("name", ""),
                                arguments=item.get("arguments", "{}"),
                                call_id=item.get("call_id", ""),
                            )
                        )
                elif event_type in {"response.failed", "error"}:
                    message = data.get("error", {}).get("message") or data.get("message") or "OpenAI request failed."
                    raise RuntimeError(message)

        result = StreamPassResult()

        def wrapper() -> Iterator[str]:
            for chunk in iterator():
                yield chunk
            result.text = "".join(text_fragments)
            result.tool_calls = tool_calls
            result.openai_response_id = response_id

        return wrapper(), result

    def _stream_anthropic(
        self,
        spec: ModelSpec,
        payload: ChatRequest,
        messages: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> tuple[Iterator[str], StreamPassResult]:
        assert self.anthropic_client is not None

        request_kwargs: dict[str, Any] = {
            "model": spec.api_name,
            "max_tokens": ANTHROPIC_MAX_TOKENS,
            "system": SYSTEM_PROMPT + _artifact_context(payload),
            "messages": messages,
            "stream": True,
        }
        if tool_choice != "none":
            request_kwargs["tools"] = _anthropic_tools()

        stream = self.anthropic_client.messages.create(**request_kwargs)

        text_fragments: list[str] = []
        tool_calls: list[NormalizedToolCall] = []
        assistant_blocks: list[dict[str, Any]] = []
        emitted_started = False

        current_block: dict[str, Any] | None = None
        current_block_text: list[str] = []
        current_tool_json: list[str] = []

        def iterator() -> Iterator[str]:
            nonlocal emitted_started, current_block
            for event in stream:
                event_type = getattr(event, "type", None)
                if event_type == "content_block_start":
                    block = _as_dict(getattr(event, "content_block", {}))
                    current_block = block
                    current_block_text.clear()
                    current_tool_json.clear()
                elif event_type == "content_block_delta":
                    delta = _as_dict(getattr(event, "delta", {}))
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        if not emitted_started:
                            emitted_started = True
                            yield sse_event({"type": "assistant.message.started", "messageId": f"draft-{uuid4()}"})
                        text_piece = delta.get("text", "")
                        text_fragments.append(text_piece)
                        current_block_text.append(text_piece)
                        yield sse_event({"type": "assistant.message.delta", "delta": text_piece})
                    elif delta_type == "input_json_delta":
                        current_tool_json.append(delta.get("partial_json", ""))
                elif event_type == "content_block_stop":
                    if current_block is None:
                        continue
                    block_type = current_block.get("type")
                    if block_type == "text":
                        assistant_blocks.append({"type": "text", "text": "".join(current_block_text)})
                    elif block_type == "tool_use":
                        arguments = "".join(current_tool_json) or "{}"
                        name = current_block.get("name", "")
                        block_id = current_block.get("id", "")
                        try:
                            parsed_input = json.loads(arguments)
                        except json.JSONDecodeError:
                            parsed_input = {}
                        assistant_blocks.append({"type": "tool_use", "id": block_id, "name": name, "input": parsed_input})
                        tool_calls.append(NormalizedToolCall(name=name, arguments=arguments, call_id=block_id))
                    current_block = None
                elif event_type == "error":
                    error_obj = _as_dict(getattr(event, "error", {}))
                    raise RuntimeError(error_obj.get("message") or "Anthropic request failed.")

        result = StreamPassResult()

        def wrapper() -> Iterator[str]:
            for chunk in iterator():
                yield chunk
            result.text = "".join(text_fragments)
            result.tool_calls = tool_calls
            result.anthropic_assistant_blocks = assistant_blocks

        return wrapper(), result

    def stream_chat(self, payload: ChatRequest) -> Iterator[str]:
        session = self.session_factory()

        try:
            try:
                spec = self._resolve_model(payload.model)
            except (ValueError, RuntimeError) as exc:
                yield sse_event({"type": "error", "message": str(exc)})
                return

            if payload.conversation_id:
                conversation = get_conversation_or_404(session, payload.conversation_id)
                created = False
            else:
                conversation = create_conversation(session, payload.message)
                created = True

            if created:
                yield sse_event({"type": "conversation.created", "conversation": serialize_conversation(conversation, session).model_dump(mode="json")})

            user_message = add_message(session, conversation, "user", payload.message)
            yield sse_event({"type": "user.message", "message": serialize_message(user_message).model_dump(mode="json")})

            yield from self._stream_from_history(session, conversation, payload, spec)
        except Exception as exc:
            session.rollback()
            yield sse_event({"type": "error", "message": str(exc)})
        finally:
            session.close()

    def regenerate_last(self, payload: RegenerateRequest) -> Iterator[str]:
        session = self.session_factory()
        try:
            try:
                spec = self._resolve_model(payload.model)
                conversation = get_conversation_or_404(session, payload.conversation_id)
                last_user = prepare_regenerate(session, conversation)
            except (ValueError, RuntimeError) as exc:
                yield sse_event({"type": "error", "message": str(exc)})
                return
            yield sse_event({"type": "user.message", "message": serialize_message(last_user).model_dump(mode="json")})
            yield sse_event({"type": "conversation.updated", "conversation": serialize_conversation(conversation, session).model_dump(mode="json")})
            yield from self._stream_from_history(session, conversation, payload, spec)
        except Exception as exc:
            session.rollback()
            yield sse_event({"type": "error", "message": str(exc)})
        finally:
            session.close()

    def rerun_after_edit(self, payload: EditLastUserRequest) -> Iterator[str]:
        session = self.session_factory()
        try:
            try:
                spec = self._resolve_model(payload.model)
                conversation = get_conversation_or_404(session, payload.conversation_id)
                updated_user = apply_edit_to_last_user(session, conversation, payload.message)
            except (ValueError, RuntimeError) as exc:
                yield sse_event({"type": "error", "message": str(exc)})
                return
            yield sse_event({"type": "user.message", "message": serialize_message(updated_user).model_dump(mode="json")})
            yield sse_event({"type": "conversation.updated", "conversation": serialize_conversation(conversation, session).model_dump(mode="json")})
            yield from self._stream_from_history(session, conversation, payload, spec)
        except Exception as exc:
            session.rollback()
            yield sse_event({"type": "error", "message": str(exc)})
        finally:
            session.close()

    def _stream_from_history(self, session, conversation, payload, spec) -> Iterator[str]:
        base_input = build_response_input(session, conversation)
        if spec.provider == "openai":
            yield from self._orchestrate_openai(session, conversation, payload, spec, base_input)
        else:
            yield from self._orchestrate_anthropic(session, conversation, payload, spec, base_input)

    def _orchestrate_openai(self, session, conversation, payload, spec, base_input) -> Iterator[str]:
        first_pass_stream, first_pass = self._stream_openai(spec, payload, base_input)
        for chunk in first_pass_stream:
            yield chunk

        tool_output_items: list[dict[str, Any]] = []
        tool_summaries: list[str] = []
        current_artifact_id = current_artifact_id_from_payload(payload.current_artifact)

        for tool_call in first_pass.tool_calls:
            if tool_call.name != "canvas_apply":
                continue
            tool_payload = CanvasToolCall.model_validate_json(tool_call.arguments)
            mutation = apply_canvas_tool(session, conversation, tool_payload, current_artifact_id=current_artifact_id)
            current_artifact_id = mutation.artifact.id
            tool_summaries.append(f"{mutation.summary} Saved in the workpad as \"{mutation.artifact.title}\".")
            artifact_payload = serialize_artifact(mutation.artifact).model_dump(mode="json")
            yield sse_event({"type": "artifact.started", "artifact": artifact_payload, "action": mutation.action, "summary": mutation.summary})
            for piece in chunk_text(mutation.artifact.content):
                yield sse_event({"type": "artifact.delta", "artifactId": mutation.artifact.id, "delta": piece})
            yield sse_event({"type": "artifact.completed", "artifact": artifact_payload})
            tool_output_items.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(
                        {
                            "artifact_id": mutation.artifact.id,
                            "title": mutation.artifact.title,
                            "content_type": mutation.artifact.content_type,
                            "version": mutation.artifact.version,
                            "summary": mutation.summary,
                        }
                    ),
                }
            )

        follow_up_text = ""
        if tool_output_items and first_pass.openai_response_id:
            follow_up_stream, follow_up = self._stream_openai(
                spec,
                payload,
                tool_output_items,
                tool_choice="none",
                previous_response_id=first_pass.openai_response_id,
            )
            for chunk in follow_up_stream:
                yield chunk
            follow_up_text = follow_up.text.strip()

        yield from self._finalize(session, conversation, first_pass.text, follow_up_text, tool_summaries)

    def _orchestrate_anthropic(self, session, conversation, payload, spec, base_input) -> Iterator[str]:
        messages = [{"role": item["role"], "content": item["content"]} for item in base_input]

        first_pass_stream, first_pass = self._stream_anthropic(spec, payload, messages)
        for chunk in first_pass_stream:
            yield chunk

        tool_results: list[dict[str, Any]] = []
        tool_summaries: list[str] = []
        current_artifact_id = current_artifact_id_from_payload(payload.current_artifact)

        for tool_call in first_pass.tool_calls:
            if tool_call.name != "canvas_apply":
                continue
            tool_payload = CanvasToolCall.model_validate_json(tool_call.arguments)
            mutation = apply_canvas_tool(session, conversation, tool_payload, current_artifact_id=current_artifact_id)
            current_artifact_id = mutation.artifact.id
            tool_summaries.append(f"{mutation.summary} Saved in the workpad as \"{mutation.artifact.title}\".")
            artifact_payload = serialize_artifact(mutation.artifact).model_dump(mode="json")
            yield sse_event({"type": "artifact.started", "artifact": artifact_payload, "action": mutation.action, "summary": mutation.summary})
            for piece in chunk_text(mutation.artifact.content):
                yield sse_event({"type": "artifact.delta", "artifactId": mutation.artifact.id, "delta": piece})
            yield sse_event({"type": "artifact.completed", "artifact": artifact_payload})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.call_id,
                    "content": json.dumps(
                        {
                            "artifact_id": mutation.artifact.id,
                            "title": mutation.artifact.title,
                            "content_type": mutation.artifact.content_type,
                            "version": mutation.artifact.version,
                            "summary": mutation.summary,
                        }
                    ),
                }
            )

        follow_up_text = ""
        if tool_results and first_pass.anthropic_assistant_blocks:
            follow_up_messages = messages + [
                {"role": "assistant", "content": first_pass.anthropic_assistant_blocks},
                {"role": "user", "content": tool_results},
            ]
            follow_up_stream, follow_up = self._stream_anthropic(spec, payload, follow_up_messages, tool_choice="none")
            for chunk in follow_up_stream:
                yield chunk
            follow_up_text = follow_up.text.strip()

        yield from self._finalize(session, conversation, first_pass.text, follow_up_text, tool_summaries)

    def _finalize(self, session, conversation, first_pass_text: str, follow_up_text: str, tool_summaries: list[str]) -> Iterator[str]:
        final_text = " ".join(part for part in [first_pass_text.strip(), follow_up_text] if part).strip()
        if not final_text:
            final_text = " ".join(tool_summaries).strip()
        if not final_text:
            final_text = "The workpad is ready."

        assistant_message = add_message(session, conversation, "assistant", final_text)
        yield sse_event({"type": "assistant.message.completed", "message": serialize_message(assistant_message).model_dump(mode="json")})
        yield sse_event({"type": "conversation.updated", "conversation": serialize_conversation(conversation, session).model_dump(mode="json")})
        yield sse_event({"type": "stream.completed"})
