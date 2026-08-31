from core.api_client import QuestLogClient


class _Response:
    ok = True
    status_code = 200
    text = ""
    content = b"{}"

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return dict(self._payload)


class _Http:
    def __init__(self, payload):
        self.payload = payload
        self.posted_json = None

    def post(self, _url, json=None, headers=None, timeout=None):
        self.posted_json = dict(json or {})
        return _Response(self.payload)


def test_create_session_requests_fresh_run_and_marks_response():
    client = QuestLogClient("key", "old-token")
    http = _Http({"token": "new-token"})
    client._http = http

    result = client.create_session("elden_ring", "reforged", build_name="Fresh Run")

    assert result["token"] == "new-token"
    assert result["_created_from_app"] is True
    assert http.posted_json["force_new"] is True
    assert http.posted_json["client_run_nonce"]


def test_create_session_refuses_current_token_reuse():
    client = QuestLogClient("key", "old-token")
    client._http = _Http({"token": "old-token"})

    result = client.create_session("elden_ring", "reforged", build_name="Fresh Run")

    assert "error" in result
    assert result["reused_token"] == "old-token"
