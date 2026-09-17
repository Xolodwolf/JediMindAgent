"""Level tagging of book chunks. Approved levels: docs/levels.md.

In «Путь джедая» chapter 6 describes the five levels in sections "6.1. Первый уровень" … "6.5. Пятый уровень",
and chapter "7. Заключение" follows. A chunk gets the level of the section open at the end of its text.
Everything outside chapter 6 — introduction, chapters 1–5, conclusion, notes — gets GENERAL_LEVEL and is
available at every user level. Sources without these headers get GENERAL_LEVEL for all chunks.
"""

import re

from jedi_mind_agent.rag.schemas import TextChunk

GENERAL_LEVEL = 0

_LEVEL_SECTION_RE = re.compile(r"^6\.([1-5])\.\s+\S+\s+уровень", re.MULTILINE | re.IGNORECASE)
# Anchored to the chapter title: a numbered list item "7." inside chapter 6 must not end the levels.
_AFTER_LEVELS_RE = re.compile(r"^7\.\s+Заключение", re.MULTILINE)


def assign_levels(chunks: list[TextChunk]) -> list[TextChunk]:
    level = GENERAL_LEVEL
    tagged: list[TextChunk] = []

    for chunk in chunks:
        events = [(match.start(), int(match.group(1))) for match in _LEVEL_SECTION_RE.finditer(chunk.text)]
        events += [(match.start(), GENERAL_LEVEL) for match in _AFTER_LEVELS_RE.finditer(chunk.text)]
        for _, value in sorted(events):
            if value == GENERAL_LEVEL and level != GENERAL_LEVEL:
                level = GENERAL_LEVEL
            # Levels only grow inside the chapter: a back reference or a missed header never lowers the tag,
            # which would expose a higher-level practice to users below it.
            elif value > level:
                level = value
        tagged.append(chunk.model_copy(update={"level": level}))

    return tagged
