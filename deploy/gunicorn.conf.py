"""One shared indexed catalog within a free-tier memory budget."""
import os

bind = "0.0.0.0:" + os.getenv("PORT", "10000")
workers = 1
worker_class = "gthread"
threads = 8
timeout = 120
graceful_timeout = 30
keepalive = 5
errorlog = "-"
# Avoid query-string logs (project selections/coordinates) on the public demo.
accesslog = None
control_socket_disable = True


def post_worker_init(worker):
    from deploy.wsgi import catalog, validate_weather
    catalog()
    validate_weather()
