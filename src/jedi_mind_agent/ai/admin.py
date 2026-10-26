import logging

from django import forms
from django.contrib import admin, messages
from langchain_core.messages import HumanMessage

from jedi_mind_agent.ai.agent import build_chat_model
from jedi_mind_agent.ai.config import LLMConfig
from jedi_mind_agent.ai.models import LLMGateway, LLMModel

logger = logging.getLogger(__name__)


class LLMGatewayForm(forms.ModelForm):
    # The key is never rendered back into the page; an empty field on edit keeps the stored key.
    api_key = forms.CharField(
        label="API-ключ",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Оставьте пустым, чтобы не менять сохранённый ключ.",
    )

    class Meta:
        model = LLMGateway
        fields = ["name", "base_url", "api_key", "timeout_seconds"]

    def clean_api_key(self) -> str:
        return self.cleaned_data["api_key"].strip() or (self.instance.api_key if self.instance.pk else "")


class LLMModelInline(admin.TabularInline):
    model = LLMModel
    extra = 0
    fields = ["title", "model_name", "temperature", "is_active"]


@admin.register(LLMGateway)
class LLMGatewayAdmin(admin.ModelAdmin):
    form = LLMGatewayForm
    list_display = ["name", "base_url", "has_api_key", "updated_at"]
    inlines = [LLMModelInline]

    @admin.display(boolean=True, description="ключ задан")
    def has_api_key(self, obj: LLMGateway) -> bool:
        return bool(obj.api_key)


@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    list_display = ["title", "model_name", "gateway", "temperature", "is_active"]
    list_filter = ["gateway", "is_active"]
    list_select_related = ["gateway"]
    actions = ["make_active", "check_connection"]

    @admin.action(description="Сделать активной")
    def make_active(self, request, queryset) -> None:
        if queryset.count() != 1:
            self.message_user(request, "Выберите ровно одну модель.", messages.ERROR)
            return
        model = queryset.get()
        model.activate()
        self.message_user(request, f"Активная модель: {model}.", messages.SUCCESS)

    @admin.action(description="Проверить подключение")
    def check_connection(self, request, queryset) -> None:
        for model in queryset.select_related("gateway"):
            if not model.gateway.api_key:
                self.message_user(request, f"{model}: у шлюза не задан API-ключ.", messages.ERROR)
                continue
            try:
                response = build_chat_model(LLMConfig.from_model(model)).invoke(
                    [HumanMessage(content="Ответь одним словом: готов.")]
                )
            except Exception as exc:
                logger.warning("LLM connection check failed for %s", model, exc_info=True)
                self.message_user(request, f"{model}: ошибка {exc.__class__.__name__}: {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{model}: ответ «{str(response.content).strip()[:80]}».", messages.SUCCESS)
