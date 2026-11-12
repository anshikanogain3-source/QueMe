from flask import jsonify, request


def api_error(message, code, status):
    return jsonify({"error": message, "code": code}), status


def json_object():
    """Return a JSON object, or None for invalid, missing, or non-object JSON."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None
