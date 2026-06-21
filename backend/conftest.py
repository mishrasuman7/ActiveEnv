"""Pytest bootstrap.

Force an in-memory SQLite DB and allow the test host *before* Django settings
load, so the suite runs hermetically without Postgres/Redis being up.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://:memory:"
os.environ["POSTGRES_DB"] = ""
os.environ["DJANGO_ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
