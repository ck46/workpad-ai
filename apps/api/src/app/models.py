from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    provider: Provider
    api_name: str
    supports_reasoning: bool = False


MODEL_CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(id="gpt-5.4", label="GPT-5.4", provider="openai", api_name="gpt-5.4", supports_reasoning=True),
    ModelSpec(id="gpt-5.4-mini", label="GPT-5.4 mini", provider="openai", api_name="gpt-5.4-mini", supports_reasoning=True),
    ModelSpec(id="claude-opus-4-7", label="Claude Opus 4.7", provider="anthropic", api_name="claude-opus-4-7"),
    ModelSpec(id="claude-sonnet-4-6", label="Claude Sonnet 4.6", provider="anthropic", api_name="claude-sonnet-4-6"),
)

DEFAULT_MODEL_ID = MODEL_CATALOG[0].id


def get_model_spec(model_id: str | None) -> ModelSpec:
    if not model_id:
        return MODEL_CATALOG[0]
    for spec in MODEL_CATALOG:
        if spec.id == model_id:
            return spec
    raise ValueError(f"Unknown model: {model_id}")
