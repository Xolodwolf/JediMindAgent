from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from jedi_mind_agent.product import service
from jedi_mind_agent.product.schemas import ExerciseOut, MessageOut, StateOut, StateResponse


@login_required
def index(request):
    return render(request, "web/index.html", {"initial": initial_data(request.user.id)})


def initial_data(user_id: int) -> dict:
    """The same payloads as GET /me/state, /me/messages and /exercises."""
    return {
        "state": StateResponse(state=StateOut.from_model(service.get_state(user_id))).model_dump(mode="json"),
        "messages": [MessageOut.from_model(m).model_dump(mode="json") for m in service.list_user_messages(user_id)],
        "exercises": [ExerciseOut.from_model(e).model_dump(mode="json") for e in service.list_exercises(user_id)],
    }


def health(request) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV})


def database_health(request) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("select 1")
    except Exception as exc:
        return JsonResponse({"status": "error", "database": exc.__class__.__name__}, status=503)
    return JsonResponse({"status": "ok", "database": "reachable"})
