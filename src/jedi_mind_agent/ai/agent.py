import logging
from functools import lru_cache

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jedi_mind_agent.ai.prompts import build_agent_prompt, build_readiness_prompt
from jedi_mind_agent.ai.schemas import AgentReply, ReadinessAssessment
from jedi_mind_agent.ai.service import fallback_answer
from jedi_mind_agent.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

History = list[tuple[str, str]]


class JediAgent:
    """Product agent. Returns validated structured output; never touches the database."""

    def __init__(self, settings: Settings) -> None:
        chat = (
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
        self._reply_llm = chat.with_structured_output(AgentReply, method="function_calling") if chat else None
        self._readiness_llm = (
            chat.with_structured_output(ReadinessAssessment, method="function_calling") if chat else None
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

    async def assess_readiness(self, *, user_context: str, history: History) -> ReadinessAssessment | None:
        if self._readiness_llm is None:
            return None

        messages = [SystemMessage(content=build_readiness_prompt(user_context)), *_to_messages(history)]
        try:
            assessment = await self._readiness_llm.ainvoke(messages)
        except Exception:
            logger.exception("Readiness assessment failed")
            return None
        return assessment if isinstance(assessment, ReadinessAssessment) else None


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
