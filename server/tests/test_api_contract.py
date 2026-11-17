"""The backend honours the HTTP contract the Android app is built against.

contract/api-contract.json is shared with the Android unit tests
(LensApiContractTest.kt), so a field renamed on one side fails a test instead of
silently breaking the app in production.
"""

import pytest

import app as be_my_lens
from support import SAMPLE_IMAGE, start_session


def send_contract_request(client, fake_openai, endpoint: dict):
    if "multipartFields" in endpoint:
        fields = endpoint["multipartFields"]
        files = {"image": ("image.jpg", SAMPLE_IMAGE, "image/jpeg")} if "image" in fields else None
        data = {name: "ما هذا؟" for name in fields if name != "image"}
        fake_openai.will_answer("model answer")
        return client.request(endpoint["method"], endpoint["path"], files=files, data=data)

    body = dict(endpoint["jsonBody"])
    if "sessionId" in body:
        body["sessionId"] = start_session(client, fake_openai)
    fake_openai.will_answer("model answer")
    return client.request(endpoint["method"], endpoint["path"], json=body)


@pytest.mark.parametrize("name", ["describe", "read", "chat", "followup", "translate_text"])
def test_endpoint_accepts_contract_request_and_returns_contract_fields(client, fake_openai, api_contract, name):
    endpoint = api_contract[name]

    response = send_contract_request(client, fake_openai, endpoint)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == set(endpoint["response"])
    assert all(isinstance(value, str) and value for value in body.values())


def test_contract_covers_every_model_backed_route(api_contract):
    served = {route.path for route in be_my_lens.app.routes if "POST" in getattr(route, "methods", set())}

    assert served == {endpoint["path"] for endpoint in api_contract.values()}
