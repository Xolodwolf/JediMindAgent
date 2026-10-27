from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    name = "jedi_mind_agent.knowledge"
    label = "knowledge"
    verbose_name = "База знаний (RAG)"

    def ready(self) -> None:
        from jedi_mind_agent.knowledge import signals  # noqa: F401 - registers the receivers
