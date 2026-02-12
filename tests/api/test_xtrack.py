import pytest
import httpx
from smartx_rfid.api.xtrack import ApiXtrack


class MockResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", response=self)

    def json(self):
        return self._data


def make_success_response(action, url, **kwargs):
    return {"msg": f"{action}_ok", "url": url, **kwargs}


class MockAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def get(self, url, params=None, headers=None):
        return MockResponse(make_success_response("get", url, params=params))

    async def post(self, url, data=None, json=None, headers=None):
        return MockResponse(make_success_response("post", url, data=data, json=json))


@pytest.mark.asyncio
async def test_get(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    api = ApiXtrack("http://testserver")
    success, response = await api.get("test", params={"a": 1})
    assert success is True
    assert response["msg"] == "get_ok"
    assert "url" in response


@pytest.mark.asyncio
async def test_post(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    api = ApiXtrack("http://testserver")
    success, response = await api.post("test", json={"b": 2})
    assert success is True
    assert response["msg"] == "post_ok"
    assert "url" in response
