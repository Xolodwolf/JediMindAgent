from django.urls import path

from jedi_mind_agent.product import api

urlpatterns = [
    path("me/state", api.state, name="api-state"),
    path("me/messages", api.messages, name="api-messages"),
    path("me/level-test", api.level_test, name="api-level-test"),
    path("me/reset", api.reset, name="api-reset"),
    path("chat/messages", api.chat_messages, name="api-chat-messages"),
    path("exercises", api.exercises, name="api-exercises"),
    path("exercises/<uuid:exercise_id>", api.exercise, name="api-exercise"),
]
