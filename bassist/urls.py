from django.urls import path

from . import views

app_name = "bassist"

urlpatterns = [
    path("", views.bassist_view, name="bassist"),
]
