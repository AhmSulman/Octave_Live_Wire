from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def bassist_view(request: HttpRequest) -> HttpResponse:
    """Render the Bassist Bot jam tool.

    All audio (mic pitch detection + bass/drum synthesis) runs in the browser
    via the Web Audio API and Tone.js — there is no server-side processing, so
    the jam stays low-latency. This view only serves the single-page app.
    """
    return render(request, "bassist/bassist.html")
