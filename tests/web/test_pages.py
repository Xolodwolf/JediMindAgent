"""Server-rendered pages: the interface shell with embedded data, auth pages, messages and error pages."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from jedi_mind_agent.product.models import UserExercise


class IndexPageTest(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user("luke", password="x-wing-pass-42")
        self.client.force_login(self.user)

    def test_initial_data_matches_the_api(self):
        UserExercise.objects.create(user=self.user, level="level_1", title="Дыхание", description="1. Вдох.")
        page = self.client.get("/")

        initial = json.loads(page.content.decode().split('type="application/json">')[1].split("</script>")[0])
        self.assertEqual(initial["state"], self.client.get("/api/v1/me/state").json())
        self.assertEqual(initial["exercises"], self.client.get("/api/v1/exercises").json())
        self.assertContains(page, '<script id="initial-data" type="application/json">')

    def test_embedded_data_is_escaped(self):
        UserExercise.objects.create(user=self.user, level="level_1", title="</script><b>x", description="…")
        page = self.client.get("/")
        self.assertNotContains(page, "</script><b>x")

    def test_topbar_links(self):
        page = self.client.get("/")
        self.assertContains(page, 'href="/accounts/password/"')
        self.assertNotContains(page, 'href="/admin/"')


class AccountPagesTest(TestCase):
    def test_registration_shows_a_message_on_the_next_page(self):
        response = self.client.post(
            "/accounts/register/",
            {"username": "leia", "password1": "Alderaan-1977!", "password2": "Alderaan-1977!"},
            follow=True,
        )
        self.assertContains(response, "Аккаунт создан.")

    def test_field_errors_are_marked_for_screen_readers(self):
        response = self.client.post(
            "/accounts/register/", {"username": "leia", "password1": "Alderaan-1977!", "password2": "other"}
        )
        self.assertContains(response, 'aria-invalid="true"')

    def test_password_change(self):
        user = get_user_model().objects.create_user("han", password="falcon-pass-42")
        self.client.force_login(user)
        self.assertContains(self.client.get("/accounts/password/"), "Смена пароля")

        response = self.client.post(
            "/accounts/password/",
            {"old_password": "falcon-pass-42", "new_password1": "Kessel-run-12", "new_password2": "Kessel-run-12"},
            follow=True,
        )

        self.assertContains(response, "Пароль изменён.")
        user.refresh_from_db()
        self.assertTrue(user.check_password("Kessel-run-12"))

    def test_custom_404(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Страница не найдена", status_code=404)
