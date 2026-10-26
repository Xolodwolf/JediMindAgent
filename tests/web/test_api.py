"""Product JSON API: auth, the level test, the agent turn and user isolation. Run: python manage.py test tests.web"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from jedi_mind_agent.ai.schemas import AgentReply, DiagnosticUpdate, ExerciseProposal
from jedi_mind_agent.knowledge.rag import RetrievalResult
from jedi_mind_agent.product import level_test as lt
from jedi_mind_agent.product import service
from jedi_mind_agent.product.enums import UserLevel
from jedi_mind_agent.product.models import ChatMessage, UserExercise, UserState


class FakeAgent:
    def __init__(self, reply: AgentReply | None = None) -> None:
        self.next_reply = reply or AgentReply(answer="Ответ агента.")
        self.rag_context = None

    def reply(self, *, user_context, history, rag_context):
        self.rag_context = rag_context
        return self.next_reply, False

    def explain_test_result(self, **_):
        return "Пояснение."


def chunk(level: int) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=f"jedi:{level}",
        text=f"Фрагмент уровня {level}",
        source_slug="jedi",
        source_title="Путь джедая",
        source_filename="jedi.pdf",
        page_start=10,
        page_end=11,
        level=level,
    )


class ApiTestCase(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user("luke", password="x-wing-pass-42")
        self.client.force_login(self.user)
        self.agent = FakeAgent()
        patcher = mock.patch("jedi_mind_agent.product.api.get_agent", return_value=self.agent)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, path: str, body: dict | None = None):
        return self.client.post(path, body or {}, content_type="application/json")

    def pass_test(self, score: int = 3, energy: int = 6) -> dict:
        self.post("/api/v1/me/level-test", {"restart": False})
        for question in lt.LEVEL_QUESTIONS:
            choice = next(i for i, option in enumerate(question.options, start=1) if option.score == score)
            self.post("/api/v1/chat/messages", {"message": str(choice), "use_rag": False})
        return self.post("/api/v1/chat/messages", {"message": str(energy), "use_rag": False}).json()


class AuthTest(TestCase):
    def test_api_requires_login(self):
        response = self.client.get("/api/v1/me/state")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Требуется вход."})

    def test_index_redirects_to_login(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_registration_logs_the_user_in(self):
        response = self.client.post(
            "/accounts/register/",
            {"username": "leia", "password1": "Alderaan-1977!", "password2": "Alderaan-1977!"},
        )
        self.assertRedirects(response, "/")
        self.assertEqual(self.client.get("/api/v1/me/state").status_code, 200)

    def test_unsafe_methods_need_the_csrf_token(self):
        get_user_model().objects.create_user("han", password="falcon-pass-42")
        client = Client(enforce_csrf_checks=True)
        client.login(username="han", password="falcon-pass-42")
        self.assertEqual(client.post("/api/v1/me/reset").status_code, 403)

        client.get("/")  # the page sets the csrftoken cookie
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post("/api/v1/me/reset", HTTP_X_CSRFTOKEN=token).status_code, 200)


class LevelTestFlowTest(ApiTestCase):
    def test_state_starts_unknown(self):
        state = self.client.get("/api/v1/me/state").json()["state"]
        self.assertEqual(state["level"], "unknown")
        self.assertEqual(state["level_rank"], 0)

    def test_first_question_has_choices(self):
        turn = self.post("/api/v1/me/level-test", {"restart": False}).json()
        [question] = turn["messages"]
        self.assertEqual(question["test"]["step"], 0)
        self.assertEqual(len(question["test"]["choices"]), 5)

    def test_unfinished_test_is_resumed_not_restarted(self):
        self.post("/api/v1/me/level-test", {"restart": False})
        self.assertEqual(self.post("/api/v1/me/level-test", {"restart": False}).json()["messages"], [])

    def test_invalid_answer_repeats_the_question(self):
        self.post("/api/v1/me/level-test", {"restart": False})
        turn = self.post("/api/v1/chat/messages", {"message": "не знаю"}).json()
        self.assertEqual(turn["messages"][1]["test"]["step"], 0)

    def test_completed_test_sets_level_and_energy(self):
        turn = self.pass_test(score=3, energy=6)
        self.assertEqual(turn["state"]["level"], "level_3")
        self.assertEqual(turn["state"]["energy_level"], 6)
        self.assertIn("Пояснение.", turn["messages"][-1]["content"])

    def test_message_without_level_starts_the_test(self):
        turn = self.post("/api/v1/chat/messages", {"message": "Привет"}).json()
        self.assertEqual(turn["messages"][0]["role"], "user")
        self.assertEqual(turn["messages"][1]["test"]["step"], 0)

    def test_validation_error_has_fastapi_shape(self):
        response = self.post("/api/v1/chat/messages", {"message": "   "})
        self.assertEqual(response.status_code, 422)
        self.assertIn("msg", response.json()["detail"][0])


class AgentTurnTest(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.pass_test(score=2)

    def test_agent_reply_updates_state_and_adds_exercise(self):
        self.agent.next_reply = AgentReply(
            answer="Попробуйте вот это.",
            diagnostic=DiagnosticUpdate(focus_level=4, main_problem="Много срочного"),
            exercise=ExerciseProposal(title="Чистый стол", description="1. Уберите лишнее.", level=UserLevel.LEVEL_1),
        )
        with mock.patch("jedi_mind_agent.knowledge.rag.retrieve", return_value=[chunk(1)]) as retrieve:
            turn = self.post("/api/v1/chat/messages", {"message": "Всё горит", "use_rag": True}).json()

        retrieve.assert_called_once_with("Всё горит", max_level=2)
        self.assertIn("Фрагмент уровня 1", self.agent.rag_context)
        self.assertEqual(turn["state"]["focus_level"], 4)
        self.assertEqual([e["title"] for e in turn["exercises_changed"]], ["Чистый стол"])
        self.assertEqual(turn["messages"][1]["sources"], [{"source_title": "Путь джедая", "page_start": 10, "page_end": 11}])

    def test_exercise_above_user_level_is_rejected(self):
        self.agent.next_reply = AgentReply(
            answer="…", exercise=ExerciseProposal(title="Стратегия", description="1. …", level=UserLevel.LEVEL_4)
        )
        turn = self.post("/api/v1/chat/messages", {"message": "Хочу больше", "use_rag": False}).json()
        self.assertEqual(turn["exercises_changed"], [])

    def test_rag_failure_does_not_break_the_answer(self):
        with mock.patch("jedi_mind_agent.knowledge.rag.retrieve", side_effect=RuntimeError("down")):
            response = self.post("/api/v1/chat/messages", {"message": "Привет", "use_rag": True})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.agent.rag_context)

    def test_test_messages_stay_out_of_agent_history(self):
        self.post("/api/v1/chat/messages", {"message": "Привет", "use_rag": False})

        chat = service.find_chat_session(self.user.id)
        history = service.list_messages(chat.id, exclude_test=True)
        # Questions and answers are excluded; the result message stays, so the agent sees the explained level.
        self.assertEqual([m.content for m in history][1:], ["Привет", "Ответ агента."])
        self.assertTrue(history[0].content.startswith("Тест завершён."))


class ExercisesAndResetTest(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.exercise = UserExercise.objects.create(user=self.user, level="level_1", title="Дыхание", description="1. Вдох.")

    def test_status_transition_and_actions(self):
        response = self.client.patch(
            f"/api/v1/exercises/{self.exercise.id}", {"status": "suitable"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["actions"], ["not_suitable"])

    def test_invalid_transition_is_a_conflict(self):
        self.exercise.status = "suitable"
        self.exercise.save()
        response = self.client.patch(
            f"/api/v1/exercises/{self.exercise.id}", {"status": "suitable"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 409)

    def test_users_cannot_touch_each_others_exercises(self):
        other = get_user_model().objects.create_user("vader", password="dark-side-42")
        self.client.force_login(other)
        self.assertEqual(self.client.get("/api/v1/exercises").json(), [])
        self.assertEqual(self.client.delete(f"/api/v1/exercises/{self.exercise.id}").status_code, 404)
        self.assertTrue(UserExercise.objects.filter(id=self.exercise.id).exists())

    def test_delete(self):
        self.assertEqual(self.client.delete(f"/api/v1/exercises/{self.exercise.id}").status_code, 204)
        self.assertFalse(UserExercise.objects.exists())

    def test_reset_deletes_only_own_data(self):
        self.pass_test()
        other = get_user_model().objects.create_user("obiwan", password="high-ground-42")
        UserExercise.objects.create(user=other, level="level_1", title="Чужое", description="…")

        state = self.post("/api/v1/me/reset").json()["state"]

        self.assertEqual(state["level"], "unknown")
        self.assertFalse(ChatMessage.objects.filter(user=self.user).exists())
        self.assertFalse(UserExercise.objects.filter(user=self.user).exists())
        self.assertTrue(UserExercise.objects.filter(user=other).exists())
        self.assertEqual(UserState.objects.get(user=self.user).energy_level, None)
