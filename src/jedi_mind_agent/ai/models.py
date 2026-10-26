from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction


class LLMGateway(models.Model):
    """An OpenAI-compatible API endpoint: OpenAI itself, a proxy, OpenRouter, a local server and so on."""

    name = models.CharField("название", max_length=100, unique=True)
    base_url = models.URLField("базовый URL", default="https://api.openai.com/v1")
    api_key = models.CharField("API-ключ", max_length=500, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(
        "таймаут запроса, с", default=60, validators=[MinValueValidator(5), MaxValueValidator(600)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "шлюз LLM"
        verbose_name_plural = "шлюзы LLM"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class LLMModel(models.Model):
    """A chat model available through a gateway. Exactly one active model answers users."""

    gateway = models.ForeignKey(LLMGateway, on_delete=models.PROTECT, related_name="models", verbose_name="шлюз")
    title = models.CharField("название", max_length=100)
    model_name = models.CharField("идентификатор модели", max_length=200, help_text="Например, gpt-4.1-mini.")
    temperature = models.FloatField(
        "температура", default=0.2, validators=[MinValueValidator(0.0), MaxValueValidator(2.0)]
    )
    is_active = models.BooleanField("активна", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "модель LLM"
        verbose_name_plural = "модели LLM"
        ordering = ["-is_active", "title"]
        constraints = [
            models.UniqueConstraint(fields=["is_active"], condition=models.Q(is_active=True), name="ai_single_active_model"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.gateway})"

    def save(self, *args, **kwargs) -> None:
        with transaction.atomic():
            if self.is_active:
                LLMModel.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
            super().save(*args, **kwargs)

    def activate(self) -> None:
        self.is_active = True
        self.save(update_fields=["is_active", "updated_at"])
