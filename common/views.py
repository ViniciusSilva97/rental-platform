from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


def home(request):
    return render(request, "home.html")


@require_GET
def health_check(request):
    """Backward-compatible liveness endpoint."""
    return health_live(request)


@require_GET
def health_live(request):
    """Report that the Django process can answer HTTP requests."""
    return JsonResponse({"status": "ok"})


@require_GET
def health_ready(request):
    """Report whether the application can serve requests that need the database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ready"})
