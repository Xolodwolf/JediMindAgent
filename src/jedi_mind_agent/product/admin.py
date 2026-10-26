from django.contrib import admin

from jedi_mind_agent.product.models import ChatMessage, ChatSession, LevelTest, UserExercise, UserState, UserStatusLog


@admin.register(UserState)
class UserStateAdmin(admin.ModelAdmin):
    list_display = ["user", "level", "energy_level", "focus_level", "diagnostic_completed_at", "updated_at"]
    list_filter = ["level"]
    search_fields = ["user__username", "main_problem"]
    list_select_related = ["user"]


@admin.register(UserExercise)
class UserExerciseAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "level", "status", "updated_at"]
    list_filter = ["status", "level"]
    search_fields = ["title", "user__username"]
    list_select_related = ["user"]


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    fields = ["created_at", "role", "content"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "user", "updated_at"]
    search_fields = ["user__username"]
    list_select_related = ["user"]
    inlines = [ChatMessageInline]


@admin.register(LevelTest)
class LevelTestAdmin(admin.ModelAdmin):
    list_display = ["user", "level", "energy_level", "created_at", "completed_at"]
    list_filter = ["level"]
    list_select_related = ["user"]


@admin.register(UserStatusLog)
class UserStatusLogAdmin(admin.ModelAdmin):
    list_display = ["user", "level", "energy_level", "focus_level", "summary", "created_at"]
    list_select_related = ["user"]
