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

    def test_get_tid_from_epc(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001", "tid": "e28000000000000000000001"})
        tid = tags.get_tid_from_epc("000000000000000000000001")
        assert tid == "e28000000000000000000001"

    def test_gtin_counts(self):
        tags = TagList()
        tags.add({"epc": "3074257bf7194e4000001a85"})
        tags.add({"epc": "3074257bf7194e4000001a86"})
        tags.add({"epc": "000000000000000000000001"})
        gtin_counts = tags.get_gtin_counts()
        assert gtin_counts.get("80614141123458") == 2
        assert gtin_counts.get("UNKNOWN") == 1

    def test_prefix(self):
        tags = TagList(prefix="3074257bf7")
        tags.add({"epc": "3074257bf7194e4000001a85"})
        tags.add({"epc": "000000000000000000000001"})
        assert len(tags) == 1

    def test_prefix_list(self):
        tags = TagList(prefix=["3074257bf7", "0000000000"])
        tags.add({"epc": "3074257bf7194e4000001a85"})
        tags.add({"epc": "000000000000000000000001"})
        tags.add({"epc": "111111111111111111111111"})
        assert len(tags) == 2

    def test_invalid_tag(self):
        tags = TagList()
        result, stored = tags.add({"epc": "0001"})
        assert result is False
        assert stored is None

    def test_unexpected_key(self):
        tags = TagList()
        result, stored = tags.add({"epc": "000000000000000000000001", "unexpected_key": "value"})
        assert result is True
        assert stored is not None
        assert stored.get("epc") == "000000000000000000000001"
        assert stored.get("unexpected_key") == "value"

    def test_epc_change(self):
        tags = TagList(unique_identifier="tid")
        tags.add({"epc": "000000000000000000000001", "tid": "e28000000000000000000001"})
        assert (
            tags.get_by_identifier("e28000000000000000000001", identifier_type="tid").get("epc")
            == "000000000000000000000001"
        )

        tags.add({"epc": "000000000000000000000002", "tid": "e28000000000000000000001"})
        assert (
            tags.get_by_identifier("e28000000000000000000001", identifier_type="tid").get("epc")
            == "000000000000000000000002"
        )

        assert len(tags) == 1

    def test_invalid_tag_on_tid_identifier(self):
        tags = TagList(unique_identifier="tid")
        result, tag_data = tags.add({"epc": "000000000000000000000001"})
        assert not result
        assert tag_data is None 

if __name__ == "__main__":
    pytest.main([__file__])
