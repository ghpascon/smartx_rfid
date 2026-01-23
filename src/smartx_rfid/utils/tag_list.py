from typing import Literal, Dict, Any, Optional, Tuple
from datetime import datetime
from threading import Lock
import logging
from pyepc import SGTIN
from smartx_rfid.schemas.tag import TagSchema


class TagList:
    """
    Thread-safe container for RFID tags.

    Tags are stored as dictionaries to allow flexible schemas per client.
    Each tag is uniquely identified by either EPC or TID.
    """

    def __init__(self, unique_identifier: Literal["epc", "tid"] = "epc", prefix: str | list | None = None):
        """
        Initialize the tag list.

        Args:
            unique_identifier: Field used as the unique tag identifier ("epc" or "tid").
        """
        if unique_identifier not in ("epc", "tid"):
            raise ValueError("unique_identifier must be 'epc' or 'tid'")

        self.unique_identifier = unique_identifier
        self._tags: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

        self.prefix: list | None = None
        if isinstance(prefix, str):
            prefix = [prefix]
        if prefix is not None:
            self.prefix = [p.lower() for p in prefix]

    def __len__(self) -> int:
        """
        Return the number of stored tags.
        """
        return len(self._tags)

    def __contains__(self, identifier: str) -> bool:
        """
        Check if a tag identifier exists in the list.
        """
        return identifier in self._tags

    def __repr__(self) -> str:
        """
        Return a string representation of the stored tags.
        """
        return repr(self.get_all())

    def add(self, tag: Dict[str, Any], device: str = "Unknown") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Add or update a tag.

        Returns:
            (True, tag_dict)   if the tag is new;
            (False, tag_dict)  if the tag already exists;
            (False, None)      if an error occurs;
        """
        try:
            # Validate Tag
            tag = TagSchema(**tag).model_dump()

            identifier_value = tag.get(self.unique_identifier)
            if not identifier_value:
                logging.warning(f"Tag missing '{self.unique_identifier}'")
                return False, None

            # Check Prefix
            if self.prefix is not None:
                epc = tag.get("epc")
                if epc is None or not any(epc.startswith(p) for p in self.prefix):
                    return False, None

            # handle tag
            with self._lock:
                if identifier_value not in self._tags:
                    stored = self._new_tag(tag, device)
                    return True, stored
                else:
                    stored = self._existing_tag(tag, device)
                    return False, stored

        except Exception as e:
            logging.error(f"[ TAG ERROR ] {e}")
            return False, None

    def _new_tag(self, tag: Dict[str, Any], device: str) -> Dict[str, Any]:
        """
        Create and store a new tag.

        Args:
            tag: Raw tag data.
            device: Source device identifier.

        Returns:
            The stored tag dictionary.
        """
        now = datetime.now()

        try:
            gtin = SGTIN.decode(tag.get("epc")).gtin
        except Exception:
            gtin = None

        stored_tag = {
            "timestamp": now,
            "device": device,
            **tag,
            "gtin": gtin,
            "count": 1,
        }

        self._tags[tag[self.unique_identifier]] = stored_tag

        return stored_tag

    def _existing_tag(self, tag: Dict[str, Any], device: str) -> Dict[str, Any]:
        """
        Update an existing tag.

        Args:
            tag: Incoming tag data.

        Returns:
            The updated stored tag.
        """
        current = self._tags[tag[self.unique_identifier]]

        current["count"] += 1
        current["timestamp"] = datetime.now()

        current["rssi"] = tag.get("rssi")
        current["ant"] = tag.get("ant")
        if not device == current["device"]:
            current["device"] = device
        if not tag.get("epc") == current.get("epc"):
            current["epc"] = tag.get("epc")

        return current

    def get_all(self) -> list[Dict[str, Any]]:
        """
        Retrieve all stored tags.

        Returns:
            A list of tag dictionaries.
        """
        with self._lock:
            return list(self._tags.values())

    def get_by_identifier(self, identifier_value: str, identifier_type: str = "epc") -> Optional[Dict[str, Any]]:
        """
        Retrieve a tag by its identifier.
        Args:
            identifier_value: The value of the identifier (EPC or TID).
            identifier_type: The type of identifier ("epc" or "tid").
        Returns:
            The tag dictionary if found, otherwise None.
        """
        if identifier_type not in ("epc", "tid"):
            identifier_type = "epc"

        if self.unique_identifier == identifier_type:
            return self._tags.get(identifier_value)

        for tag in self._tags.values():
            if tag.get(identifier_type) == identifier_value:
                return tag

        return None

    def clear(self) -> None:
        """
        Remove all stored tags.
        """
        with self._lock:
            self._tags.clear()

    def remove_tags_before_timestamp(self, timestamp: datetime) -> None:
        """
        Remove tags older than a given timestamp.

        Args:
            timestamp: Minimum timestamp to keep.
        """
        with self._lock:
            self._tags = {k: v for k, v in self._tags.items() if v.get("timestamp") and v["timestamp"] >= timestamp}

    def remove_tags_by_device(self, device: str) -> None:
        """
        Remove all tags associated with a specific device.

        Args:
            device: Device identifier.
        """
        with self._lock:
            self._tags = {k: v for k, v in self._tags.items() if v.get("device") != device}

    def get_tid_from_epc(self, epc: str) -> Optional[str]:
        """
        Retrieve the TID associated with a given EPC.

        Args:
            epc: EPC value.

        Returns:
            The TID if found, otherwise None.
        """
        with self._lock:
            tag = self._tags.get(epc)
            if tag:
                return tag.get("tid")
            return None

    def get_epcs(self) -> list[str]:
        """
        Retrieve a list of all stored EPCs.

        Returns:
            A list of EPC strings.
        """
        with self._lock:
            return [tag["epc"] for tag in self._tags.values() if "epc" in tag]

    def get_gtin_counts(self) -> Dict[str, int]:
        """
        Retrieve counts of tags grouped by GTIN.

        Returns:
            A dictionary mapping GTINs to their respective counts.
        """
        gtin_counts: Dict[str, int] = {}
        with self._lock:
            for tag in self._tags.values():
                gtin = tag.get("gtin")
                if gtin is None:
                    gtin = "UNKNOWN"
                gtin_counts[gtin] = gtin_counts.get(gtin, 0) + 1

        return gtin_counts
