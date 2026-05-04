import pytest

from smartx_rfid.utils import TagList
from datetime import datetime, timedelta


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
        result, stored = tags.add({"epc": "g001"})
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

    def test_null_on_tid_identifier(self):
        tags = TagList(unique_identifier="tid")
        result, tag_data = tags.add({"epc": "000000000000000000000001"})
        assert result
        assert tag_data.get("tid") == "_NULL_000000000000000000000001"
        assert tag_data.get("epc") == "000000000000000000000001"

    def test_protected(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001", "protected": True})
        tags.add({"epc": "000000000000000000000002", "protected": False})
        tags.add({"epc": "000000000000000000000003"})
        assert tags.get_by_identifier("000000000000000000000001").get("protected") is True
        assert tags.get_by_identifier("000000000000000000000002").get("protected") is False
        assert tags.get_by_identifier("000000000000000000000003").get("protected") is False

    def test_change_gtin(self):
        tags = TagList(unique_identifier="tid")

        tags.add({"epc": "000000000000000000000001", "tid": "e28000000000000000000001"})
        assert tags.get_by_identifier("e28000000000000000000001", identifier_type="tid").get("gtin") is None

        tags.add({"epc": "3035e1ddd0011fc000000003", "tid": "e28000000000000000000001"})
        assert tags.get_by_identifier("e28000000000000000000001", identifier_type="tid").get("gtin") == "07894900011517"

    def test_remove_tag_by_identifier_returns_list_unique_key(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001"})

        removed = tags.remove_tag_by_identifier("000000000000000000000001", identifier_type="epc")

        assert isinstance(removed, list)
        assert len(removed) == 1
        assert removed[0].get("epc") == "000000000000000000000001"
        assert len(tags) == 0

    def test_remove_tag_by_identifier_returns_multiple_for_same_epc(self):
        tags = TagList(unique_identifier="tid")
        tags.add({"epc": "000000000000000000000001", "tid": "e28000000000000000000001"})
        tags.add({"epc": "000000000000000000000001", "tid": "e28000000000000000000002"})
        tags.add({"epc": "000000000000000000000002", "tid": "e28000000000000000000003"})

        removed = tags.remove_tag_by_identifier("000000000000000000000001", identifier_type="epc")

        assert isinstance(removed, list)
        assert len(removed) == 2
        assert all(tag.get("epc") == "000000000000000000000001" for tag in removed)
        assert len(tags) == 1
        remaining = tags.get_all()
        assert len(remaining) == 1
        assert remaining[0].get("epc") == "000000000000000000000002"

    def test_remove_tags_before_timestamp_returns_removed_list(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001"})
        tags.add({"epc": "000000000000000000000002"})

        old_timestamp = datetime.now() - timedelta(hours=1)
        tags._tags["000000000000000000000001"]["timestamp"] = old_timestamp

        removed = tags.remove_tags_before_timestamp(datetime.now() - timedelta(minutes=1))

        assert isinstance(removed, list)
        assert len(removed) == 1
        assert removed[0].get("epc") == "000000000000000000000001"
        assert len(tags) == 1
        assert tags.get_by_identifier("000000000000000000000002") is not None

    def test_remove_tags_by_device_returns_removed_list(self):
        tags = TagList()
        tags.add({"epc": "000000000000000000000001"}, device="reader_a")
        tags.add({"epc": "000000000000000000000002"}, device="reader_a")
        tags.add({"epc": "000000000000000000000003"}, device="reader_b")

        removed = tags.remove_tags_by_device("reader_a")

        assert isinstance(removed, list)
        assert len(removed) == 2
        assert all(tag.get("device") == "reader_a" for tag in removed)
        assert len(tags) == 1
        assert tags.get_by_identifier("000000000000000000000003") is not None

    def test_get_all_limit(self):
        tags = TagList()
        for i in range(10):
            tags.add({"epc": f"00000000000000000000000{i}"})
        assert len(tags.get_all()) == 10
        assert len(tags.get_all(limit=5)) == 5
        assert len(tags.get_all(limit=0)) == 0

    def test_get_all_limit_none(self):
        tags = TagList()
        for i in range(10):
            tags.add({"epc": f"00000000000000000000000{i}"})
        assert len(tags.get_all(limit=None)) == 10

    def test_get_all_limit_negative(self):
        tags = TagList()
        for i in range(10):
            tags.add({"epc": f"00000000000000000000000{i}"})
        assert len(tags.get_all(limit=-1)) == 10

    def test_get_epcs_limit(self):
        tags = TagList()
        for i in range(10):
            tags.add({"epc": f"00000000000000000000000{i}"})
        assert len(tags.get_epcs()) == 10
        assert len(tags.get_epcs(limit=3)) == 3
        assert len(tags.get_epcs(limit=0)) == 0

    def test_get_epcs_limit_none(self):
        tags = TagList()
        for i in range(10):
            tags.add({"epc": f"00000000000000000000000{i}"})
        assert len(tags.get_epcs(limit=None)) == 10

    def test_get_epcs_limit_negative(self):
        tags = TagList()
        for i in range(10):
            tags.add({"epc": f"00000000000000000000000{i}"})
        assert len(tags.get_epcs(limit=-5)) == 10


if __name__ == "__main__":
    pytest.main([__file__])
