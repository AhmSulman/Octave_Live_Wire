from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("backing_track_creator.urls")),
    path("pad/", include("pad.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
