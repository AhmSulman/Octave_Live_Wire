from django.urls import path
from . import views

app_name = "backing_track_creator"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("media-player/", views.media_player_view, name="media_player"),
    path("piano/", views.piano_learner_view, name="piano_learner"),
    path("guitar/", views.guitar_fretboard_view, name="guitar_fretboard"),
    path("backing-track/", views.backing_track_view, name="backing_track"),
    # API endpoints
    path("api/analyze/", views.analyze_audio, name="analyze_audio"),
    path("api/fretboard/", views.get_fretboard_data, name="fretboard_data"),
    path("api/compose/", views.auto_compose, name="auto_compose"),
]
