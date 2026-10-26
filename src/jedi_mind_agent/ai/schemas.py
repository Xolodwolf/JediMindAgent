from pydantic import BaseModel, Field

from jedi_mind_agent.product.enums import UserLevel


# Structured outputs of the product agent. Value ranges are deliberately not enforced here:
# an out-of-range number must not discard the whole reply, the domain service drops it instead.
# Field descriptions are sent to the model as part of the tool schema, so they are in Russian.


class DiagnosticUpdate(BaseModel):
    # No level field: the level is set only by the level test.
    energy_level: int | None = Field(default=None, description="Мыслетопливо, от 1 до 10.")
    focus_level: int | None = Field(default=None, description="Способность сосредоточиться, от 1 до 10.")
    main_problem: str | None = Field(default=None, description="Главная проблема пользователя, одно короткое предложение.")
    time_limit_minutes: int | None = Field(default=None, description="Сколько минут в день пользователь готов уделять практикам.")


class ExerciseProposal(BaseModel):
    title: str = Field(description="Короткое название упражнения.")
    description: str = Field(description="Зачем нужно, пронумерованные шаги, ожидаемый результат. Адаптировано под пользователя.")
    level: UserLevel | None = Field(default=None, description="Уровень, к которому относится практика; не выше уровня пользователя.")
    estimated_minutes: int | None = Field(default=None, description="Примерная длительность в минутах.")


class AgentReply(BaseModel):
    answer: str = Field(description="Сообщение, которое увидит пользователь.")
    diagnostic: DiagnosticUpdate | None = Field(default=None, description="Новые сведения о состоянии пользователя.")
    exercise: ExerciseProposal | None = Field(default=None, description="Одно упражнение, если его уместно предложить.")
