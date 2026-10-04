"""WSGI entry point: `gunicorn wsgi:app` (production) or `flask --app wsgi run` (development)."""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from resumeiq import create_app  # noqa: E402

app = create_app()
