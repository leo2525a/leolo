from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # 這是為了確保只有在主進程中才啟動排程器，而不是在 runserver 的重載進程中
        import os
        from . import scheduler

        if os.environ.get('RUN_MAIN'):
            print("Starting scheduler from apps.py...")
            scheduler.start_scheduler()