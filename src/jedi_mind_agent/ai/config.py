from dataclasses import dataclass

from jedi_mind_agent.ai.models import LLMModel


@dataclass(frozen=True)
class LLMConfig:
    """A snapshot of the active model and its gateway. Hashable, so agents can be cached per configuration."""

    model_name: str
    base_url: str
    api_key: str
    temperature: float
    timeout_seconds: int

    @classmethod
    def from_model(cls, model: LLMModel) -> "LLMConfig":
        return cls(
            model_name=model.model_name,
            base_url=model.gateway.base_url,
            api_key=model.gateway.api_key,
            temperature=model.temperature,
            timeout_seconds=model.gateway.timeout_seconds,
        )


def get_llm_config() -> LLMConfig | None:
    """The active model from the admin; None when no model is active."""
    model = LLMModel.objects.select_related("gateway").filter(is_active=True).first()
    return LLMConfig.from_model(model) if model else None
