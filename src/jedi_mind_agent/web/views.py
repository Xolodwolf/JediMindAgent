from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render


@login_required
def index(request):
    return render(request, "web/index.html")


def health(request) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV})


def database_health(request) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("select 1")
    except Exception as exc:
        return JsonResponse({"status": "error", "database": exc.__class__.__name__}, status=503)
    return JsonResponse({"status": "ok", "database": "reachable"})
