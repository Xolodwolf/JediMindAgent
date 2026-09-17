"""Level test: a fixed questionnaire with deterministic scoring. Approved text: docs/level-test.md.

The test runs in the chat one question at a time. Steps 0-9 are level questions, step 10 is the mental fuel scale.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from jedi_mind_agent.product.enums import LEVEL_BY_RANK, LEVEL_RANK, LEVEL_TITLES, UserLevel


@dataclass(frozen=True)
class Option:
    text: str
    score: int


@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[Option, ...]  # in display order


def _question(text: str, display_order: tuple[int, ...], *options_by_level: str) -> Question:
    # Options are written in level order so the text is easy to review against docs/level-test.md.
    # display_order fixes a shuffled order, so the "best" answer is not always the last one.
    return Question(text, tuple(Option(options_by_level[level - 1], level) for level in display_order))


LEVEL_QUESTIONS: tuple[Question, ...] = (
    _question(
        "Какое утверждение лучше всего описывает ваше состояние в последние 2–3 недели?",
        (2, 4, 1, 5, 3),
        "Я не успеваю выполнять даже необходимый минимум.",
        "Я едва-едва успеваю выполнить необходимую текучку, но на долгосрочные планы не остаётся сил.",
        "Я успеваю разобраться с необходимой текучкой и даже изредка могу посвящать силы долгосрочным планам.",
        "Я вполне продуктивно продвигаюсь к своим долгосрочным целям. Завалы если и случаются, то нечасто.",
        "Всё происходит легко и естественно, и временами мне кажется, что лучше и быть не может.",
    ),
    _question(
        "Сколько вашего времени уходит на срочные дела?",
        (3, 1, 5, 2, 4),
        "Почти всё — всё горит, и даже срочное я не успеваю.",
        "Практически всё; на остальное не остаётся сил.",
        "Большая часть, но иногда получается заняться важным несрочным.",
        "Срочное под контролем, основное время уходит на запланированные важные дела.",
        "Срочных «пожаров» почти нет, время распределяется естественно.",
    ),
    _question(
        "Как часто задачи теряются или вспоминаются в последний момент?",
        (4, 2, 5, 1, 3),
        "Постоянно — я плохо понимаю, что вообще нужно сделать.",
        "Регулярно: что-то забываю, и потом приходится разгребать последствия.",
        "Изредка — в целом все обязательства у меня записаны.",
        "Почти никогда: есть система, которой я доверяю.",
        "Не задумываюсь об этом — система работает незаметно и подстраивается под меня.",
    ),
    _question(
        "Как часто у вас случаются авралы?",
        (1, 3, 5, 4, 2),
        "Аврал — моё постоянное состояние.",
        "Несколько раз в неделю, и обычно они застают врасплох.",
        "Бывают, но многие «пожары» удаётся заметить заранее.",
        "Редко, и обычно они предсказуемы.",
        "Почти не бывает, а неожиданности я часто обращаю себе на пользу.",
    ),
    _question(
        "Как вы обычно себя чувствуете в конце рабочего дня?",
        (5, 2, 4, 1, 3),
        "Выжат, тревожно, трудно переключиться или уснуть.",
        "Устал, отдыха хватает впритык.",
        "Устаю, но к утру восстанавливаюсь.",
        "Обычно остаются силы на личные дела и цели.",
        "Чувствую себя наполненным — работа скорее даёт энергию.",
    ),
    _question(
        "Бывает ли у вас время подумать не о самих делах, а о том, как их лучше делать?",
        (2, 5, 3, 1, 4),
        "Нет, я едва успеваю реагировать на происходящее.",
        "Редко: мысли появляются, но сил что-то менять нет.",
        "Иногда получается что-то улучшить в своих процессах.",
        "Регулярно пересматриваю и улучшаю свои подходы.",
        "Подстраиваю свою технику под себя постоянно и естественно.",
    ),
    _question(
        "Что происходит с вашими долгосрочными планами?",
        (3, 5, 1, 4, 2),
        "Их нет, или о них просто некогда думать.",
        "Они есть, но постоянно откладываются.",
        "Изредка продвигаю их, но нерегулярно.",
        "Планомерно продвигаюсь, шаги понятны.",
        "Движение к ним происходит легко, часто без специальных усилий.",
    ),
    _question(
        "Насколько ваши текущие дела связаны с тем, чего вы действительно хотите?",
        (4, 1, 3, 5, 2),
        "Не до этого — лишь бы продержаться.",
        "Большинство дел навязаны обстоятельствами.",
        "Начинаю замечать лишние дела, но отказываться от них пока не получается.",
        "Регулярно отсекаю лишнее и сверяю дела со своими целями.",
        "Почти всё, чем я занимаюсь, мне действительно важно.",
    ),
    _question(
        "Как у вас с отвлечениями — уведомления, чаты, соцсети?",
        (1, 4, 2, 5, 3),
        "Реагирую на всё сразу, сосредоточиться не удаётся.",
        "Часто отвлекаюсь и с трудом возвращаюсь к делу.",
        "Часть отвлечений ограничил, но периодически срываюсь.",
        "Отвлечения под контролем, умею выделять время на сосредоточенную работу.",
        "Вниманием управлять легко, отвлечения почти не мешают.",
    ),
    _question(
        "Что происходит, когда планы рушит что-то неожиданное?",
        (5, 3, 1, 2, 4),
        "Всё окончательно выходит из-под контроля.",
        "Выбивает надолго, потом долго разгребаю последствия.",
        "Неприятно, но через какое-то время возвращаюсь в колею.",
        "Спокойно перестраиваю планы — запас на неожиданности обычно есть.",
        "Часто нахожу в неожиданном новые возможности.",
    ),
)

ENERGY_QUESTION = (
    "Оцените свой запас мыслетоплива прямо сейчас: сколько у вас сил принимать решения и сосредотачиваться?"
)
ENERGY_SCALE_HINT = "1 — ни на что нет сил, 5 — хватает на текучку, 10 — полон сил."
ENERGY_MAX = 10

ENERGY_STEP = len(LEVEL_QUESTIONS)
TOTAL_STEPS = len(LEVEL_QUESTIONS) + 1

INTRO = (
    "Давайте определим ваш уровень джедайской зрелости по книге «Путь джедая». "
    f"Это {TOTAL_STEPS} коротких вопросов. Отвечайте за последние 2–3 недели: "
    "нажмите на вариант или отправьте его номер."
)
INVALID_ANSWER = "Не получилось распознать ответ. Нажмите на вариант или отправьте его номер."

_CHOICE_RE = re.compile(r"^\s*(\d{1,2})\s*[.)]?\s*$")


def is_scale(step: int) -> bool:
    return step == ENERGY_STEP


def choices(step: int) -> list[str]:
    if is_scale(step):
        return [str(value) for value in range(1, ENERGY_MAX + 1)]
    return [option.text for option in LEVEL_QUESTIONS[step].options]


def question_text(step: int) -> str:
    text = f"{ENERGY_QUESTION}\n{ENERGY_SCALE_HINT}" if is_scale(step) else LEVEL_QUESTIONS[step].text
    return f"Вопрос {step + 1} из {TOTAL_STEPS}. {text}"


def parse_choice(text: str, step: int) -> int | None:
    """Only an option number is accepted; free text is never interpreted, so scoring stays reproducible."""
    match = _CHOICE_RE.match(text)
    if match is None:
        return None
    choice = int(match.group(1))
    return choice if 1 <= choice <= len(choices(step)) else None


def answer_label(step: int, choice: int) -> str:
    if is_scale(step):
        return f"{choice} из {ENERGY_MAX}"
    return f"{choice}. {LEVEL_QUESTIONS[step].options[choice - 1].text}"


def score(step: int, choice: int) -> int:
    return LEVEL_QUESTIONS[step].options[choice - 1].score


def level_from_scores(scores: Sequence[int]) -> UserLevel:
    """Mean score rounded down. The level is the ceiling of practices, so the estimate is deliberately cautious."""
    if len(scores) != len(LEVEL_QUESTIONS) or any(not 1 <= value <= 5 for value in scores):
        raise ValueError(f"Expected {len(LEVEL_QUESTIONS)} scores from 1 to 5, got {list(scores)}")
    return LEVEL_BY_RANK[sum(scores) // len(scores)]


def describe_answers(answers: Sequence[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {LEVEL_QUESTIONS[step].text} — {LEVEL_QUESTIONS[step].options[answer['choice'] - 1].text}"
        for step, answer in enumerate(answers)
    )


def result_text(level: UserLevel, energy_level: int, explanation: str | None) -> str:
    parts = [
        "Тест завершён.",
        f"Ваш уровень: {LEVEL_RANK[level]} — «{LEVEL_TITLES[level]}».\nМыслетопливо: {energy_level} из {ENERGY_MAX}.",
    ]
    if explanation:
        parts.append(explanation)
    parts.append("Расскажите, что сейчас беспокоит больше всего, — подберу первую практику.")
    return "\n\n".join(parts)
