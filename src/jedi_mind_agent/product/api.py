"""Product JSON API for the web interface. The current user is the logged-in Django user (session auth + CSRF)."""

import json
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from pydantic import BaseModel, ValidationError

from jedi_mind_agent.ai.agent import get_agent
from jedi_mind_agent.knowledge import rag
from jedi_mind_agent.product import service
from jedi_mind_agent.product.schemas import (
    ChatMessageIn,
    ChatTurnOut,
    ExerciseOut,
    ExercisePatchIn,
    LevelTestStartIn,
    MessageOut,
    StateOut,
    StateResponse,
)


def error(status: int, detail) -> JsonResponse:
    # Same shape as FastAPI errors, so the web interface shows `detail` as is.
    return JsonResponse({"detail": detail}, status=status)


def api_view(handlers: dict[str, tuple[type[BaseModel] | None, Callable]]) -> Callable:
    """One URL, a handler per HTTP method. A handler gets the request, the validated body (or None) and URL kwargs."""

    def view(request: HttpRequest, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return error(401, "Требуется вход.")
        if request.method not in handlers:
            return error(405, "Метод не поддерживается.")

        body_model, handler = handlers[request.method]
        body = None
        if body_model is not None:
            try:
                body = body_model.model_validate(json.loads(request.body or b"{}"))
            except json.JSONDecodeError:
                return error(400, "Тело запроса должно быть JSON.")
            except ValidationError as exc:
                return error(422, [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()])

        try:
            result = handler(request, body, **kwargs)
        except service.NotFoundError as exc:
            return error(404, str(exc))
        except service.DomainError as exc:
            return error(409, str(exc))

        if result is None:
            return HttpResponse(status=204)
        if isinstance(result, list):
            return JsonResponse([item.model_dump(mode="json") for item in result], safe=False)
        return JsonResponse(result.model_dump(mode="json"))

    return view


def _state(request, _body) -> StateResponse:
    return StateResponse(state=StateOut.from_model(service.get_state(request.user.id)))


def _messages(request, _body) -> list[MessageOut]:
    return [MessageOut.from_model(message) for message in service.list_user_messages(request.user.id)]


def _start_level_test(request, body: LevelTestStartIn) -> ChatTurnOut:
    return _turn_out(service.start_level_test(user_id=request.user.id, restart=body.restart))


def _reset(request, _body) -> StateResponse:
    return StateResponse(state=StateOut.from_model(service.reset_user(request.user.id)))


def _send_message(request, body: ChatMessageIn) -> ChatTurnOut:
    turn = service.handle_chat_message(
        user_id=request.user.id,
        text=body.message,
        agent=get_agent(),
        retrieve=_retrieve if body.use_rag else None,
    )
    return _turn_out(turn)


def _exercises(request, _body) -> list[ExerciseOut]:
    return [ExerciseOut.from_model(exercise) for exercise in service.list_exercises(request.user.id)]


def _update_exercise(request, body: ExercisePatchIn, exercise_id) -> ExerciseOut:
    exercise = service.change_exercise_status(user_id=request.user.id, exercise_id=exercise_id, target=body.status)
    return ExerciseOut.from_model(exercise)


def _delete_exercise(request, _body, exercise_id) -> None:
    service.delete_exercise(user_id=request.user.id, exercise_id=exercise_id)


state = api_view({"GET": (None, _state)})
messages = api_view({"GET": (None, _messages)})
level_test = api_view({"POST": (LevelTestStartIn, _start_level_test)})
reset = api_view({"POST": (None, _reset)})
chat_messages = api_view({"POST": (ChatMessageIn, _send_message)})
exercises = api_view({"GET": (None, _exercises)})
exercise = api_view({"PATCH": (ExercisePatchIn, _update_exercise), "DELETE": (None, _delete_exercise)})


def _turn_out(turn: service.ChatTurn) -> ChatTurnOut:
    return ChatTurnOut(
        messages=[MessageOut.from_model(message) for message in turn.messages],
        state=StateOut.from_model(turn.state),
        exercises_changed=[ExerciseOut.from_model(exercise) for exercise in turn.new_exercises],
    )


def _retrieve(query: str, max_level: int) -> list[rag.RetrievalResult]:
    return rag.retrieve(query, max_level=max_level)
