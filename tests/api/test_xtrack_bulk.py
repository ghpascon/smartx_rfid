import pytest

from smartx_rfid.api.xtrack import ApiXtrack


@pytest.mark.asyncio
async def test_register_objects_bulk_constructs_xml_and_posts():
    api = ApiXtrack("https://example.local")
    captured = {}

    async def fake_post(self, data=None, headers=None, **kwargs):
        captured["data"] = data
        captured["headers"] = headers
        return True, {"status": "ok"}

    api.post = fake_post.__get__(api, ApiXtrack)

    objects = [
        {"IDCODE": "A1", "DESCRIPTION": "Obj A"},
        {"IDCODE": "B2", "DESCRIPTION": "Obj B"},
    ]

    success, response = await api.register_objects_bulk(objects)

    assert success is True
    assert "<command>ImportObject</command>" in captured["data"]
    assert "<object><IDCODE>A1</IDCODE><DESCRIPTION>Obj A</DESCRIPTION></object>" in captured["data"]
    assert "<object><IDCODE>B2</IDCODE><DESCRIPTION>Obj B</DESCRIPTION></object>" in captured["data"]
    assert captured["headers"] == {"Content-Type": "application/xml"}


@pytest.mark.asyncio
async def test_move_objects_bulk_constructs_xml_and_posts():
    api = ApiXtrack("https://example.local")
    captured = {}

    async def fake_post(self, data=None, headers=None, **kwargs):
        captured["data"] = data
        captured["headers"] = headers
        return True, {"status": "ok"}

    api.post = fake_post.__get__(api, ApiXtrack)

    moves = [
        {"idcode": "X1", "location_id": "L1"},
        {"idcode": "X2", "location_id": "L2"},
    ]

    success, response = await api.move_objects_bulk(moves)

    assert success is True
    assert "<command>MoveLocation</command>" in captured["data"]
    assert "<object>X1</object><location>L1</location>" in captured["data"]
    assert "<object>X2</object><location>L2</location>" in captured["data"]
    assert captured["headers"] == {"Content-Type": "application/xml"}
