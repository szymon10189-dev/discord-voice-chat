import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
_default_workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
workers = int(os.environ.get("WEB_CONCURRENCY", _default_workers))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
accesslog = "-"
errorlog = "-"
capture_output = True
