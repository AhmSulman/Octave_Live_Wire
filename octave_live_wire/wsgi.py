import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "octave_live_wire.settings")

if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
    import django
    django.setup()
    from django.core.management import call_command
    call_command("migrate", verbosity=0)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
