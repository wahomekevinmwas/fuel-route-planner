import json

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.geocoding import GeocodeError
from .services.planner import PlanError, build_plan
from .services.routing import RoutingError


def _read_params(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            raise ValueError("Request body must be valid JSON.")
    else:
        data = request.GET
    start = str(data.get("start") or "").strip()
    finish = str(data.get("finish") or "").strip()
    if not start or not finish:
        raise ValueError("Both 'start' and 'finish' are required, e.g. 'Chicago, IL' or '41.88,-87.63'.")
    return start, finish


@csrf_exempt
@require_http_methods(["GET", "POST"])
def route_plan(request):
    """GET /api/route/?start=...&finish=...   or   POST {"start": "...", "finish": "..."}"""
    try:
        start, finish = _read_params(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        return JsonResponse(build_plan(start, finish))
    except GeocodeError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except PlanError as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    except RoutingError as exc:
        return JsonResponse({"error": str(exc)}, status=502)


@require_http_methods(["GET"])
def route_map(request):
    """Browser page: draws the route and the fuel stops on a Leaflet map."""
    start = request.GET.get("start", "").strip()
    finish = request.GET.get("finish", "").strip()
    api_url = ""
    if start and finish:
        from urllib.parse import urlencode

        api_url = f"{reverse('route-plan')}?{urlencode({'start': start, 'finish': finish})}"
    return render(request, "planner/map.html", {"start": start, "finish": finish, "api_url": api_url})
