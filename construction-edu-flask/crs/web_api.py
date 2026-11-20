"""Session-protected browser API for the research workbench."""
import hmac
import os
import secrets
from datetime import timedelta
from functools import wraps

from flask import jsonify, request, session

from crs.model_gateway import ModelError, configured
from crs.osha_documents import ingest, search, sources
from crs.workbench import Workbench
from crs_engine import CRSInputError, CRSNotFound, CRSVersionConflict


def register_web_api(app):
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("CRS_WEB_INSECURE_LOCAL") != "1"
    app.permanent_session_lifetime = timedelta(hours=4)

    def error(exc):
        if isinstance(exc, CRSNotFound):
            status = 404
        elif isinstance(exc, CRSVersionConflict):
            status = 409
        elif isinstance(exc, ModelError):
            status = 502
        else:
            status = 400
        return jsonify({"error": str(exc)}), status

    def authenticated(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("wb_authenticated"):
                return jsonify({"error": "Sign in to the research workbench"}), 401
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                sent = request.headers.get("X-CSRF-Token", "")
                expected = session.get("wb_csrf", "")
                if not expected or not hmac.compare_digest(sent, expected):
                    return jsonify({"error": "CSRF validation failed"}), 403
            if os.getenv("CRS_REQUIRE_DURABLE_DB") == "1" and not os.getenv("CRS_DATABASE_URL"):
                return jsonify({"error": "Durable database is required"}), 503
            try:
                return fn(*args, **kwargs)
            except (CRSInputError, CRSNotFound, CRSVersionConflict, ModelError, ValueError) as exc:
                return error(exc)
        return wrapper

    def payload():
        if not request.is_json or not isinstance(request.get_json(silent=True), dict):
            raise CRSInputError("JSON object required")
        return request.get_json()

    @app.post("/api/workbench/login")
    def wb_login():
        password = os.getenv("CRS_WEB_PASSWORD", "")
        signing = os.getenv("CRS_WEB_SESSION_SECRET", "")
        if len(password) < 16 or len(signing) < 32:
            return jsonify({"error": "Web login is disabled until the server secrets are configured"}), 503
        data = request.get_json(silent=True)
        supplied = data.get("password", "") if isinstance(data, dict) else ""
        if not isinstance(supplied, str) or not hmac.compare_digest(password, supplied):
            return jsonify({"error": "Invalid credentials"}), 401
        app.secret_key = signing
        session.clear()
        session.permanent = True
        session["wb_authenticated"] = True
        session["wb_csrf"] = secrets.token_urlsafe(32)
        return jsonify({"authenticated": True, "csrf": session["wb_csrf"]})

    # Flask must know the signing secret before reading a session cookie.
    # Configure this in the Azure Container App, never in client JavaScript.
    app.secret_key = os.getenv("CRS_WEB_SESSION_SECRET") or None

    @app.get("/api/workbench/session")
    @authenticated
    def wb_session():
        return jsonify({"authenticated": True, "csrf": session["wb_csrf"]})

    @app.post("/api/workbench/logout")
    @authenticated
    def wb_logout():
        session.clear()
        return jsonify({"authenticated": False})

    @app.get("/api/workbench/status")
    @authenticated
    def wb_status():
        w = Workbench()
        return jsonify({"model_configured": configured(), "documents": sources(w.engine),
                        "cases": w.list_cases(), "human_review_required": True})

    @app.post("/api/workbench/ingest")
    @authenticated
    def wb_ingest():
        data = payload()
        sections = data.get("sections", ["1926.650", "1926.651", "1926.652"])
        try:
            result = ingest(Workbench().engine, sections=sections)
        except (OSError, TimeoutError, UnicodeError) as exc:
            return jsonify({"error": "OSHA source download failed; no synthetic substitute was used"}), 502
        return jsonify({"ingested": result})

    @app.post("/api/workbench/search")
    @authenticated
    def wb_search():
        data = payload()
        return jsonify(search(Workbench().engine, data.get("query"), data.get("limit", 7)))

    @app.post("/api/workbench/scenarios")
    @authenticated
    def wb_create():
        result = Workbench().create(payload().get("text"))
        return jsonify(result), 201

    @app.get("/api/workbench/scenarios/<sid>")
    @authenticated
    def wb_get(sid):
        return jsonify(Workbench().view(sid, request.args.get("branch", "base")))

    @app.post("/api/workbench/scenarios/<sid>/messages")
    @authenticated
    def wb_reply(sid):
        data = payload()
        return jsonify(Workbench().revise(
            sid, data.get("text"), data.get("expected_version"),
            data.get("branch", "base")))

    @app.post("/api/workbench/scenarios/<sid>/branches")
    @authenticated
    def wb_branch(sid):
        data = payload()
        return jsonify(Workbench().branch(
            sid, data.get("name"), data.get("from_branch", "base"))), 201
    @app.post("/api/workbench/scenarios/<sid>/review")
    @authenticated
    def wb_review(sid):
        data = payload()
        return jsonify(Workbench().review(sid, data.get("branch", "base"),
                                            data.get("decision_id"),
                                            data.get("action"), data.get("note", "")))
