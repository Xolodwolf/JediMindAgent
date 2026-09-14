from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jedi_mind_agent.ai.prompts import SYSTEM_PROMPT, build_rag_prompt
from jedi_mind_agent.core.config import Settings


class OpenAIChatService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
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

    async def respond(self, message: str, *, rag_context: str | None = None) -> tuple[str, bool]:
        if self._chat is None:
            return self._fallback_answer("OPENAI_API_KEY is not configured."), True

        system_prompt = build_rag_prompt(rag_context) if rag_context else SYSTEM_PROMPT

        try:
            response = await self._chat.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message),
                ]
            )
        except Exception as exc:
            return self._fallback_answer(f"LangChain/OpenAI error: {exc.__class__.__name__}."), True

        return str(response.content), False

    @staticmethod
    def _fallback_answer(reason: str) -> str:
        return (
            "OpenAI API сейчас недоступен для приложения. "
            "Проверьте переменную OPENAI_API_KEY и настройки контейнера. "
            f"Техническая причина: {reason}"
        )
