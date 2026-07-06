from flask import jsonify


def ok(data=None, message=""):
    return jsonify({"status": "ok", "data": data if data is not None else {}, "message": message})


def error(message, code="VALIDATION_ERROR", status=400, details=None):
    return jsonify({"error": message, "code": code, "details": details or {}}), status
