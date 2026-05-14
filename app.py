"""Kaskad Web UI v2 — Flask + Basic Auth + NAT CRUD."""
from __future__ import annotations

import functools
import logging
import os

from flask import Flask, Response, jsonify, render_template, request

from kaskad_store import (
    iptables_chain_dump,
    load_rules,
    normalize_rule,
    save_rules,
    startup_resync,
    sync_iptables,
)
from system_info import collect_services_rows, collect_system_payload

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

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
    title = os.environ.get("KASKAD_UI_TITLE", "Kaskad Web UI v2").strip()
    return render_template("index.html", panel_url=PANEL_URL, ui_title=title)


def _need_auth_json(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if auth is None or not check_auth(auth.username or "", auth.password or ""):
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


@app.get("/api/system")
@_need_auth_json
def api_system():
    return jsonify(collect_system_payload())


@app.get("/api/services")
@_need_auth_json
def api_services():
    return jsonify({"services": collect_services_rows()})


@app.get("/api/clients")
@_need_auth_json
def api_clients_list():
    return jsonify({"clients": load_rules()})


@app.post("/api/clients")
@_need_auth_json
def api_clients_add():
    body = request.get_json(force=True, silent=True) or {}
    try:
        rule = normalize_rule(body)
        rules = load_rules()
        rules.append(rule)
        ok, msg = sync_iptables(rules)
        if not ok:
            return jsonify({"error": msg}), 500
        save_rules(rules)
        return jsonify({"client": rule}), 201
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.put("/api/clients/<cid>")
@_need_auth_json
def api_clients_update(cid: str):
    body = request.get_json(force=True, silent=True) or {}
    rules = load_rules()
    idx = next((i for i, r in enumerate(rules) if str(r.get("id")) == cid), None)
    if idx is None:
        return jsonify({"error": "не найдено"}), 404
    try:
        rule = normalize_rule(body, rid=cid)
        rules[idx] = rule
        ok, msg = sync_iptables(rules)
        if not ok:
            return jsonify({"error": msg}), 500
        save_rules(rules)
        return jsonify({"client": rule})
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.delete("/api/clients/<cid>")
@_need_auth_json
def api_clients_delete(cid: str):
    rules = load_rules()
    new_rules = [r for r in rules if str(r.get("id")) != cid]
    if len(new_rules) == len(rules):
        return jsonify({"error": "не найдено"}), 404
    ok, msg = sync_iptables(new_rules)
    if not ok:
        return jsonify({"error": msg}), 500
    save_rules(new_rules)
    return jsonify({"ok": True})


@app.post("/api/iptables/sync")
@_need_auth_json
def api_iptables_sync():
    rules = load_rules()
    ok, msg = sync_iptables(rules)
    if not ok:
        return jsonify({"error": msg}), 500
    return jsonify({"ok": True})


@app.get("/api/iptables/raw")
@_need_auth_json
def api_iptables_raw():
    return jsonify({"raw": iptables_chain_dump()})


startup_resync()


def main():
    port = int(os.environ.get("PORT", "8088"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
