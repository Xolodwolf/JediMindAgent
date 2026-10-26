import logging
from functools import lru_cache

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jedi_mind_agent.ai.config import LLMConfig, get_llm_config
from jedi_mind_agent.ai.prompts import build_agent_prompt, build_test_result_prompt
from jedi_mind_agent.ai.schemas import AgentReply

logger = logging.getLogger(__name__)

History = list[tuple[str, str]]

NOT_CONFIGURED = "В админке не выбрана активная модель LLM или у её шлюза не задан API-ключ."


class JediAgent:
    """Product agent. Returns validated structured output; never touches the database."""

    def __init__(self, config: LLMConfig | None) -> None:
        self._chat = build_chat_model(config) if config and config.api_key else None
        # function_calling is the most widely supported mode among OpenAI-compatible providers.
        self._reply_llm = (
            self._chat.with_structured_output(AgentReply, method="function_calling") if self._chat else None
        )

    def reply(self, *, user_context: str, history: History, rag_context: str | None) -> tuple[AgentReply, bool]:
        if self._reply_llm is None:
            return AgentReply(answer=fallback_answer(NOT_CONFIGURED)), True

        messages = [SystemMessage(content=build_agent_prompt(user_context, rag_context)), *_to_messages(history)]
        try:
            reply = self._reply_llm.invoke(messages)
        except Exception as exc:
            logger.exception("Agent reply failed")
            return AgentReply(answer=fallback_answer(f"LangChain/OpenAI error: {exc.__class__.__name__}.")), True

        if not isinstance(reply, AgentReply):
            logger.error("Agent returned no structured reply: %r", reply)
            return AgentReply(answer=fallback_answer("The model returned no structured reply.")), True
        return reply, False

    def explain_test_result(self, *, level_rank: int, level_title: str, energy_level: int, answers: str) -> str | None:
        """Plain-text explanation of an already computed test result; None when the model is unavailable."""
        if self._chat is None:
            return None

        messages = [
            SystemMessage(content=build_test_result_prompt()),
            HumanMessage(
                content=(
                    f"Уровень: {level_rank} — «{level_title}».\n"
                    f"Мыслетопливо: {energy_level} из 10.\n\n"
                    f"Ответы пользователя:\n{answers}"
                )
            ),
        ]
        try:
            response = self._chat.invoke(messages)
        except Exception:
            logger.exception("Test result explanation failed")
            return None
        return str(response.content).strip() or None


def build_chat_model(config: LLMConfig) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model_name,
        temperature=config.temperature,
        timeout=config.timeout_seconds,
    )


def fallback_answer(reason: str) -> str:
    return (
        "Модель сейчас недоступна для приложения. "
        "Проверьте активную модель и шлюз LLM в админке. "
        f"Техническая причина: {reason}"
    )


def _to_messages(history: History) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for role, content in history:
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def get_agent() -> JediAgent:
    # The configuration is read on every request, so a model switched in the admin applies immediately.
    return _agent_for(get_llm_config())


@lru_cache(maxsize=8)
def _agent_for(config: LLMConfig | None) -> JediAgent:
    return JediAgent(config)
