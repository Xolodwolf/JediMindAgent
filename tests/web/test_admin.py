"""Admin settings: the active LLM model and the book queue. Run: python manage.py test tests.web"""

import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from jedi_mind_agent.ai.agent import JediAgent, get_agent
from jedi_mind_agent.ai.config import get_llm_config
from jedi_mind_agent.ai.models import LLMGateway, LLMModel
from jedi_mind_agent.knowledge.models import Book, BookStatus, RagSettings

PDF = b"%PDF-1.4\n%fake but with a valid header\n"


class LLMModelTest(TestCase):
    def setUp(self) -> None:
        self.gateway = LLMGateway.objects.create(name="OpenAI", api_key="sk-test")

    def test_only_one_model_is_active(self):
        first = LLMModel.objects.create(gateway=self.gateway, title="A", model_name="a", is_active=True)
        second = LLMModel.objects.create(gateway=self.gateway, title="B", model_name="b", is_active=True)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(get_llm_config().model_name, "b")

        first.activate()
        second.refresh_from_db()
        self.assertFalse(second.is_active)
        self.assertEqual(get_llm_config().model_name, "a")

    def test_no_active_model_gives_a_fallback_agent(self):
        self.assertIsNone(get_llm_config())
        reply, used_fallback = get_agent().reply(user_context="", history=[], rag_context=None)
        self.assertTrue(used_fallback)
        self.assertIn("админке", reply.answer)

    def test_switching_the_model_applies_without_restart(self):
        LLMModel.objects.create(gateway=self.gateway, title="A", model_name="a", is_active=True)
        first = get_agent()
        LLMModel.objects.create(gateway=self.gateway, title="B", model_name="b", is_active=True)
        self.assertIsNot(get_agent(), first)
        self.assertIsInstance(get_agent(), JediAgent)


class AdminTestCase(TestCase):
    def setUp(self) -> None:
        self.admin = get_user_model().objects.create_superuser("admin", password="admin-pass-42")
        self.client.force_login(self.admin)
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)


class GatewayAdminTest(AdminTestCase):
    def test_empty_key_on_edit_keeps_the_stored_key(self):
        gateway = LLMGateway.objects.create(name="Proxy", base_url="https://llm.example/v1", api_key="sk-secret")
        page = self.client.get(f"/admin/ai/llmgateway/{gateway.pk}/change/")
        self.assertNotContains(page, "sk-secret")

        self.client.post(
            f"/admin/ai/llmgateway/{gateway.pk}/change/",
            {
                "name": "Proxy",
                "base_url": "https://llm.example/v1",
                "api_key": "",
                "timeout_seconds": 60,
                "models-TOTAL_FORMS": 0,
                "models-INITIAL_FORMS": 0,
            },
        )
        gateway.refresh_from_db()
        self.assertEqual(gateway.api_key, "sk-secret")


class BookAdminTest(AdminTestCase):
    def upload(self, content: bytes = PDF, name: str = "jedi-path.pdf", title: str = "Путь джедая"):
        return self.client.post(
            "/admin/knowledge/book/add/",
            {"title": title, "slug": "", "file": SimpleUploadedFile(name, content, content_type="application/pdf")},
        )

    def test_upload_queues_the_book_with_current_chroma_settings(self):
        settings = RagSettings.load()
        settings.chroma_collection = "books_v2"
        settings.save()

        response = self.upload()

        self.assertEqual(response.status_code, 302)
        book = Book.objects.get()
        self.assertEqual(book.status, BookStatus.PENDING)
        self.assertEqual(book.revision, 1)
        self.assertEqual(book.slug, "jedi-path")  # the Cyrillic title gives no slug, the file name does
        self.assertEqual(book.ingest_config, {"host": "chroma", "port": 8000, "collection": "books_v2"})

    def test_change_page_shows_worker_results_and_fixes_the_slug(self):
        self.upload()
        book = Book.objects.get()
        Book.objects.filter(pk=book.pk).update(status=BookStatus.READY, chunks_by_level={"0": 3, "2": 5})

        page = self.client.get(f"/admin/knowledge/book/{book.pk}/change/")

        self.assertContains(page, "общие: 3, уровень 2: 5")
        self.assertNotContains(page, 'name="slug"')

    def test_not_a_pdf_is_rejected(self):
        response = self.upload(content=b"hello", name="notes.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Это не PDF-файл.")
        self.assertFalse(Book.objects.exists())

    def test_reindex_and_remove_actions(self):
        self.upload()
        book = Book.objects.get()
        Book.objects.filter(pk=book.pk).update(status=BookStatus.READY)

        self.client.post("/admin/knowledge/book/", {"action": "reindex", "_selected_action": [book.pk]})
        book.refresh_from_db()
        self.assertEqual((book.status, book.revision), (BookStatus.PENDING, 2))

        self.client.post("/admin/knowledge/book/", {"action": "remove", "_selected_action": [book.pk]})
        book.refresh_from_db()
        self.assertEqual((book.status, book.revision), (BookStatus.DELETING, 3))
        # The row stays until the worker has removed the chunks from ChromaDB.
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())

    def test_rag_settings_page_reports_an_unreachable_service(self):
        response = self.client.get("/admin/knowledge/ragsettings/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RAG-сервис недоступен")
