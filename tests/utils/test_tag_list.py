import pytest

from smartx_rfid.utils import TagList
from datetime import datetime


class TestSERIAL:
    def test_create_from_epc(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001"})
        assert len(tags) == 1

        tag = tags.get_by_identifier("000000000000000000000001")
        assert tag is not None
        assert tag.get("epc") == "000000000000000000000001"
        assert tag.get("tid") is None
        assert tag.get("ant") is None
        assert tag.get("rssi") is None
        assert tag.get("count") == 1
        assert tag.get("device") == "Unknown"
        assert tag.get("gtin") is None
        assert isinstance(tag.get("timestamp"), datetime)

    def create_from_tag_dict(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001", "tid": "e28000000000000000000001", "ant": 1, "rssi": -70})
        assert len(tags) == 1

        tag = tags.get_by_identifier("000000000000000000000001")
        assert tag is not None
        assert tag.get("epc") == "000000000000000000000001"
        assert tag.get("tid") == "e28000000000000000000001"
        assert tag.get("ant") == 1
        assert tag.get("rssi") == -70
        assert tag.get("count") == 1
        assert tag.get("device") == "Unknown"
        assert tag.get("gtin") is None
        assert isinstance(tag.get("timestamp"), datetime)

    def test_gtin(self):
        tags = TagList()
        tags.add({"epc": "3074257bf7194e4000001a85"})
        tag = tags.get_by_identifier("3074257bf7194e4000001a85")
        assert tag is not None
        assert tag.get("gtin") == "80614141123458"

    def test_multiple_tags(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001"})
        tags.add({"epc": "000000000000000000000002"})
        tags.add({"epc": "000000000000000000000003"})
        assert len(tags) == 3

    def test_duplicate_tag(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001"})
        tags.add({"epc": "000000000000000000000001"})
        assert len(tags) == 1


if __name__ == "__main__":
    pytest.main([__file__])
