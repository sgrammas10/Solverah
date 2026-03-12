from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def init_rate_limiter(app):
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
    )
    @limiter.request_filter
    def _skip_preflight():
        return request.method == "OPTIONS"
    return limiter
