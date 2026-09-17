import logging
from functools import lru_cache

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jedi_mind_agent.ai.prompts import build_agent_prompt, build_test_result_prompt
from jedi_mind_agent.ai.schemas import AgentReply
from jedi_mind_agent.ai.service import fallback_answer
from jedi_mind_agent.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

History = list[tuple[str, str]]


class JediAgent:
    """Product agent. Returns validated structured output; never touches the database."""

    def __init__(self, settings: Settings) -> None:
        self._chat = (
            ChatOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_chat_model,
                temperature=0.2,
            )
            if settings.openai_api_key
            else None
        )
        # function_calling is the most widely supported mode among OpenAI-compatible providers.
        self._reply_llm = (
            self._chat.with_structured_output(AgentReply, method="function_calling") if self._chat else None
        )

    async def reply(self, *, user_context: str, history: History, rag_context: str | None) -> tuple[AgentReply, bool]:
        if self._reply_llm is None:
            return AgentReply(answer=fallback_answer("OPENAI_API_KEY is not configured.")), True

        messages = [SystemMessage(content=build_agent_prompt(user_context, rag_context)), *_to_messages(history)]
        try:
            reply = await self._reply_llm.ainvoke(messages)
        except Exception as exc:
            logger.exception("Agent reply failed")
            return AgentReply(answer=fallback_answer(f"LangChain/OpenAI error: {exc.__class__.__name__}.")), True

        if not isinstance(reply, AgentReply):
            logger.error("Agent returned no structured reply: %r", reply)
            return AgentReply(answer=fallback_answer("The model returned no structured reply.")), True
        return reply, False

    async def explain_test_result(
        self, *, level_rank: int, level_title: str, energy_level: int, answers: str
    ) -> str | None:
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
            response = await self._chat.ainvoke(messages)
        except Exception:
            logger.exception("Test result explanation failed")
            return None
        return str(response.content).strip() or None


def _to_messages(history: History) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for role, content in history:
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


@lru_cache(maxsize=1)
def get_agent() -> JediAgent:
    return JediAgent(get_settings())
