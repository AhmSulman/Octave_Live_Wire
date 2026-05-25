from django.urls import path
from . import views

app_name = "pad"

urlpatterns = [
    path("", views.pad_view, name="pad"),
    path("run/", views.run_code, name="run_code"),
]
