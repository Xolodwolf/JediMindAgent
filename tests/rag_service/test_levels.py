"""Book chunk level tagging and PDF text normalization. Run: docker compose exec rag python -m unittest discover -s tests/rag_service -t ."""

import unittest

from rag_service.levels import GENERAL_LEVEL, assign_levels
from rag_service.pdf import normalize_text
from rag_service.schemas import TextChunk


def chunks(*texts: str) -> list[TextChunk]:
    return [
        TextChunk(chunk_index=i, text=text, page_start=i + 1, page_end=i + 1, chunk_hash=str(i))
        for i, text in enumerate(texts)
    ]


def levels(*texts: str) -> list[int]:
    return [chunk.level for chunk in assign_levels(chunks(*texts))]


class AssignLevelsTest(unittest.TestCase):
    def test_book_structure(self):
        self.assertEqual(
            levels(
                "Введение и главы 1–5.",
                "5.8. Как работать с книгой\n\n6.1. Первый уровень. Все горит…\nОсновная задача…",
                "Практики первого уровня.",
                "6.2. Второй уровень. Ночь простоять да день продержаться",
                "6.3. Третий уровень. Есть свет в конце тоннеля",
                "6.4. Четвертый уровень. Планомерно к намеченным целям",
                "6.5. Пятый уровень. Естественно, спонтанно и все во благо",
                "Рис. 163. Ловкое комбо\n\n7. Заключение\nВ начале этой книги…",
                "Примечания",
            ),
            [0, 1, 1, 2, 3, 4, 5, GENERAL_LEVEL, GENERAL_LEVEL],
        )

    def test_level_is_taken_at_the_end_of_the_chunk(self):
        self.assertEqual(levels("конец первого уровня\n6.2. Второй уровень. Ночь…\nначало второго"), [2])

    def test_back_reference_does_not_lower_the_level(self):
        self.assertEqual(levels("6.3. Третий уровень. Есть свет", "6.1. Первый уровень. Все горит"), [3, 3])

    def test_missed_header_still_raises_the_level(self):
        self.assertEqual(levels("6.1. Первый уровень. Все горит", "6.3. Третий уровень. Есть свет"), [1, 3])

    def test_numbered_list_item_does_not_end_the_chapter(self):
        self.assertEqual(levels("6.4. Четвертый уровень. Планомерно", "6. Шестой шаг\n7. Седьмой шаг"), [4, 4])

    def test_header_must_start_a_line(self):
        self.assertEqual(levels("см. раздел 6.2. Второй уровень, там подробнее"), [0])

    def test_conclusion_before_levels_is_ignored(self):
        self.assertEqual(levels("7. Заключение из оглавления", "6.1. Первый уровень. Все горит"), [0, 1])

    def test_source_without_headers_is_general(self):
        self.assertEqual(levels("Другая книга.", "Ещё текст."), [0, 0])


class NormalizeTextTest(unittest.TestCase):
    def test_tabs_and_repeated_spaces_become_one_space(self):
        self.assertEqual(normalize_text("6.1.\tПервый\tуровень.  Все горит…"), "6.1. Первый уровень. Все горит…")

    def test_empty_lines_are_dropped_and_lines_are_trimmed(self):
        self.assertEqual(normalize_text("  первая \t\n\n \t \nвторая"), "первая\nвторая")


if __name__ == "__main__":
    unittest.main()
