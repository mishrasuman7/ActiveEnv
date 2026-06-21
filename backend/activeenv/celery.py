"""Celery application for ActiveEnv.

Probes and re-probes run as async tasks so the UI can show the
're-probe later → turns green' beat without blocking a request.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "activeenv.settings")

app = Celery("activeenv")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
