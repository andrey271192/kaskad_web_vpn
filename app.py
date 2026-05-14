"""Мини-сайт про каскад AmneziaWG: только страница и HTTP Basic Auth."""
from __future__ import annotations

import functools
import os

from flask import Flask, Response, render_template, request

USER = os.environ.get("BASIC_AUTH_USER", "user1").strip() or "user1"
PW = os.environ.get("BASIC_AUTH_PASSWORD", "").strip()
REALM = os.environ.get("BASIC_AUTH_REALM", "kaskad").strip() or "kaskad"
PANEL_URL = os.environ.get("PANEL_URL", "").strip()

app = Flask(__name__)


def check_auth(u: str, p: str) -> bool:
    if not PW:
        return False
    return u == USER and p == PW


def requires_auth(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if auth is None or not check_auth(auth.username or "", auth.password or ""):
            return Response(
                "Требуется вход\n",
                401,
                {"WWW-Authenticate": f'Basic realm="{REALM}"'},
                mimetype="text/plain; charset=utf-8",
            )
        return view(*args, **kwargs)

    return wrapped


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
@requires_auth
def index():
    return render_template("index.html", panel_url=PANEL_URL)


def main():
    port = int(os.environ.get("PORT", "8088"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
