from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from jedi_mind_agent.ai.prompts import SYSTEM_PROMPT
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

    async def respond(self, message: str) -> tuple[str, bool]:
        if self._chat is None:
            return self._fallback_answer("OPENAI_API_KEY is not configured."), True

        try:
            response = await self._chat.ainvoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
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
