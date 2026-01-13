from typing import Literal, Dict, Any, Optional
from dataclasses import dataclass, asdict
from smartx_rfid.schemas.tag import TagSchema
from datetime import datetime
from pyepc import SGTIN
import logging
from threading import Lock


@dataclass
class StoredTag:
    epc: str
    tid: Optional[str] = None
    rssi: Optional[int] = None
    ant: Optional[int] = None
    timestamp: datetime = datetime.now()
    device: str = "Unknown"
    count: int = 1
    gtin: str = ""


class TagList:
    def __init__(self, unique_identifier: Literal["epc", "tid"] = "epc"):
        if unique_identifier not in ("epc", "tid"):
            raise ValueError("unique_identifier must be 'epc' or 'tid'")

        self.unique_identifier = unique_identifier
        self._tags: Dict[str, StoredTag] = {}
        self._lock = Lock()

    def add(self, tag: dict, device: str = "Unknown") -> bool:
        """
        Add or update a tag in the list.

        Returns True if the tag is new, False if it already existed.
        """
        try:
            tag_data = TagSchema(**tag)
            tag = tag_data.model_dump()
        except Exception as e:
            logging.warning(f"Invalid tag data: {e}")
            raise ValueError(f"Invalid tag data: {e}")

        identifier_value = tag.get(self.unique_identifier)
        if not identifier_value:
            raise ValueError(f"Tag missing '{self.unique_identifier}'")

        with self._lock:
            if identifier_value not in self._tags:
                self._new_tag(tag, device)
                return True
            else:
                self._existing_tag(tag)
                return False

    def _new_tag(self, tag: dict, device: str):
        """Add a brand new tag."""
        # Decode GTIN if possible
        try:
            gtin = SGTIN.decode(tag.get("epc")).gtin
        except Exception:
            gtin = None

        identifier_value = tag[self.unique_identifier]
        stored_tag = StoredTag(
            epc=tag.get("epc", ""),
            tid=tag.get("tid"),
            rssi=tag.get("rssi"),
            ant=tag.get("ant"),
            timestamp=datetime.now(),
            device=device,
            count=1,
            gtin=gtin,
        )
        self._tags[identifier_value] = stored_tag
        logging.info(f"[ TAG ] - {asdict(stored_tag)}")

    def _existing_tag(self, tag: dict):
        """Update an existing tag."""
        identifier_value = tag[self.unique_identifier]
        current_tag = self._tags[identifier_value]
        current_tag.count += 1
        current_tag.timestamp = datetime.now()

        tag_rssi = tag.get("rssi")
        if tag_rssi is not None:
            if current_tag.rssi is None or abs(tag_rssi) < abs(current_tag.rssi):
                current_tag.rssi = tag_rssi
                current_tag.ant = tag.get("ant")

    def get_all(self):
        """Get all stored tags as dicts."""
        with self._lock:
            return [asdict(tag) for tag in self._tags.values()]

    def get_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get a tag by its unique identifier."""
        with self._lock:
            tag = self._tags.get(identifier)
            return asdict(tag) if tag else None

    def get_epcs(self):
        """Get all EPCs in the list."""
        with self._lock:
            return [tag.epc for tag in self._tags.values()]

    def get_tids(self):
        """Get all TIDs in the list."""
        with self._lock:
            return [tag.tid for tag in self._tags.values()]

    def clear(self):
        """Clear all tags from the list."""
        with self._lock:
            self._tags.clear()

    def remove_tags_before_timestamp(self, timestamp: datetime):
        """Remove tags added before a specific timestamp."""
        with self._lock:
            self._tags = {k: v for k, v in self._tags.items() if v.timestamp >= timestamp}

    def remove_tags_by_device(self, device: Optional[str] = None):
        """Remove tags added by a specific device."""
        with self._lock:
            self._tags = {k: v for k, v in self._tags.items() if v.device != device}

    def __len__(self):
        return len(self._tags)

    def __contains__(self, identifier: str):
        return identifier in self._tags

    def __repr__(self):
        """Show a friendly representation of the tag list."""
        with self._lock:
            return repr([asdict(tag) for tag in self._tags.values()])
