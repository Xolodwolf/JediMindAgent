"""Level test questionnaire and scoring. Run: docker compose exec app python -m unittest discover -s tests"""

import unittest

from jedi_mind_agent.product import level_test as lt
from jedi_mind_agent.product.enums import UserLevel


def answer_with(scores: list[int]) -> list[int]:
    """Displayed option numbers that give the requested score for each question."""
    return [
        next(index for index, option in enumerate(question.options, start=1) if option.score == score)
        for question, score in zip(lt.LEVEL_QUESTIONS, scores, strict=True)
    ]


class QuestionnaireTest(unittest.TestCase):
    def test_ten_questions_and_an_energy_step(self):
        self.assertEqual(len(lt.LEVEL_QUESTIONS), 10)
        self.assertEqual(lt.ENERGY_STEP, 10)
        self.assertEqual(lt.TOTAL_STEPS, 11)

    def test_every_question_has_one_option_per_level(self):
        for question in lt.LEVEL_QUESTIONS:
            with self.subTest(question=question.text):
                self.assertEqual(sorted(option.score for option in question.options), [1, 2, 3, 4, 5])
                self.assertEqual(len({option.text for option in question.options}), 5)

    def test_best_answer_is_not_always_in_the_same_position(self):
        positions = {
            next(i for i, option in enumerate(question.options) if option.score == 5) for question in lt.LEVEL_QUESTIONS
        }
        self.assertGreater(len(positions), 1)

    def test_first_question_is_the_book_self_assessment(self):
        texts = {option.text for option in lt.LEVEL_QUESTIONS[0].options}
        self.assertIn("Я не успеваю выполнять даже необходимый минимум.", texts)


class ScoringTest(unittest.TestCase):
    def test_examples_from_the_approved_document(self):
        cases = [
            ([2, 2, 2, 3, 2, 2, 3, 2, 2, 2], UserLevel.LEVEL_2),
            ([3, 3, 4, 3, 4, 3, 3, 4, 3, 3], UserLevel.LEVEL_3),
            ([4, 4, 5, 4, 4, 4, 5, 4, 4, 4], UserLevel.LEVEL_4),
            ([2, 3, 3, 3, 3, 3, 3, 3, 3, 3], UserLevel.LEVEL_2),  # mean 2.9 is rounded down
        ]
        for scores, level in cases:
            with self.subTest(scores=scores):
                self.assertEqual(lt.level_from_scores(scores), level)

    def test_extremes(self):
        self.assertEqual(lt.level_from_scores([1] * 10), UserLevel.LEVEL_1)
        self.assertEqual(lt.level_from_scores([5] * 10), UserLevel.LEVEL_5)

    def test_invalid_scores_are_rejected(self):
        for scores in ([3] * 9, [3] * 11, [0] + [3] * 9, [6] + [3] * 9):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                lt.level_from_scores(scores)

    def test_scores_follow_the_shuffled_display_order(self):
        wanted = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        choices = answer_with(wanted)
        self.assertEqual([lt.score(step, choice) for step, choice in enumerate(choices)], wanted)


class ParseChoiceTest(unittest.TestCase):
    def test_accepted_formats(self):
        for text, expected in (("3", 3), (" 2 ", 2), ("4.", 4), ("5)", 5), ("1", 1)):
            with self.subTest(text=text):
                self.assertEqual(lt.parse_choice(text, 0), expected)

    def test_rejected_answers(self):
        for text in ("0", "6", "два", "3 варианта", "", "3.5", "-1"):
            with self.subTest(text=text):
                self.assertIsNone(lt.parse_choice(text, 0))

    def test_energy_scale_accepts_one_to_ten(self):
        self.assertEqual(lt.parse_choice("10", lt.ENERGY_STEP), 10)
        self.assertEqual(lt.parse_choice("7", lt.ENERGY_STEP), 7)
        self.assertIsNone(lt.parse_choice("11", lt.ENERGY_STEP))


class TextsTest(unittest.TestCase):
    def test_question_text_has_progress(self):
        self.assertTrue(lt.question_text(0).startswith("Вопрос 1 из 11. "))
        self.assertTrue(lt.question_text(lt.ENERGY_STEP).startswith("Вопрос 11 из 11. "))

    def test_answer_label_shows_the_chosen_option(self):
        question = lt.LEVEL_QUESTIONS[1]
        self.assertEqual(lt.answer_label(1, 2), f"2. {question.options[1].text}")
        self.assertEqual(lt.answer_label(lt.ENERGY_STEP, 4), "4 из 10")

    def test_result_text_names_the_level_without_codes(self):
        text = lt.result_text(UserLevel.LEVEL_3, 6, "Пояснение.")
        self.assertIn("3 — «Есть свет в конце тоннеля»", text)
        self.assertIn("Мыслетопливо: 6 из 10", text)
        self.assertNotIn("level_", text)


if __name__ == "__main__":
    unittest.main()
