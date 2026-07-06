from flask import g, jsonify, has_request_context


def ok(data=None, message=""):
    return jsonify({"status": "ok", "data": data if data is not None else {}, "message": message})


def error(message, code="VALIDATION_ERROR", status=400, details=None):
    request_id = getattr(g, "request_id", "") if has_request_context() else ""
    return jsonify({"error": message, "code": code, "details": details or {}, "request_id": request_id}), status
