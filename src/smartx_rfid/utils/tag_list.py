from itertools import islice
from typing import Literal, Dict, Any, Optional, Tuple, Callable
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

    def __init__(
        self,
        unique_identifier: Literal["epc", "tid"] = "epc",
        prefix: str | list | None = None,
        fix_24_char_epc: bool = False,
    ):
        """
        Initialize the tag list.

        Args:
            unique_identifier: Field used as the unique tag identifier ("epc" or "tid").
        """
        if unique_identifier not in ("epc", "tid"):
            raise ValueError("unique_identifier must be 'epc' or 'tid'")

        self.unique_identifier = unique_identifier
        self._tags: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[str, Dict[str, str]] = {
            "epc": {},
            "tid": {},
        }
        self._lock = Lock()

        self.prefix: tuple[str, ...] | None = None
        if isinstance(prefix, str):
            prefix = [prefix]
        if prefix is not None:
            self.prefix = tuple(p.lower() for p in prefix)

        self.fix_24_char_epc = fix_24_char_epc

        self.chip_map: Dict[str, str] = {
            "e2801114": "Impinj Monza 4i",
            "e2801100": "Impinj Monza 4D",
            "e2801105": "Impinj Monza 4QT",
            "e2801160": "Impinj Monza R6",
            "e2801170": "Impinj Monza R6-P",
            "e2801191": "Impinj M730",
            "e2806915": "Impinj M730",
            "e2801190": "Impinj M750",
            "e28011a0": "Impinj M770",
            "e28011c0": "Impinj M780",
            "e28011c1": "Impinj M781",
            "e28011b0": "Impinj M800",
            "e2806894": "NXP Ucode 8",
            "e2806994": "NXP Ucode 8m",
            "e2806995": "NXP Ucode 9",
            "e2806a16": "NXP Ucode 9XE",
            "e2806897": "NXP Ucode 9XM",
            "e2003412": "Alien Higgs 3",
            "e2003811": "Alien Higgs-EC",
            "e2003821": "Alien Higgs 9",
            "e2803821": "Alien Higgs 9",
            "e2803813": "Alien Higgs 10",
        }

    def __len__(self) -> int:
        """
        Return the number of stored tags.
        """
        with self._lock:
            return len(self._tags)

    def __contains__(self, identifier: str) -> bool:
        """
        Check if a tag identifier exists in the list.
        """
        with self._lock:
            return identifier in self._tags

    def __repr__(self) -> str:
        """
        Return a string representation of the stored tags.
        """
        return repr(self.get_all())

    def _index_add(self, primary_key: str, tag: Dict[str, Any]) -> None:
        epc = tag.get("epc")
        tid = tag.get("tid")
        if epc:
            self._index["epc"][epc] = primary_key
        if tid:
            self._index["tid"][tid] = primary_key

    def _index_remove(self, primary_key: str, tag: Dict[str, Any]) -> None:
        epc = tag.get("epc")
        tid = tag.get("tid")
        if epc:
            self._index["epc"].pop(epc, None)
        if tid:
            self._index["tid"].pop(tid, None)

    def _index_move(
        self, field: Literal["epc", "tid"], primary_key: str, old_value: Optional[str], new_value: Optional[str]
    ) -> None:
        if old_value == new_value:
            return
        if old_value:
            self._index[field].pop(old_value, None)
        if new_value:
            self._index[field][new_value] = primary_key

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
            if self.fix_24_char_epc and not len(tag.get("epc")) == 24:
                logging.warning("Tag EPC must have exactly 24 characters")
                return False, None

            identifier_value = tag.get(self.unique_identifier)
            if not identifier_value:
                if self.unique_identifier == "epc":
                    logging.warning(f"Tag missing '{self.unique_identifier}'")
                    return False, None
                else:
                    # treat null tids
                    identifier_value = f"_NULL_{tag.get('epc', 'UNKNOWN')}"
                    tag[self.unique_identifier] = identifier_value

            # Check Prefix
            if self.prefix is not None:
                epc = tag.get("epc")
                if epc is None or not epc.startswith(self.prefix):
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

        tid_val = tag.get("tid")
        tid_key = "Unknown"
        if tid_val:
            tid_key = tid_val[:8].lower()
            if not tid_key.startswith("e"):
                tid_key = "e" + tid_key
        chip_name = self.chip_map.get(tid_key, "Unknown")
        stored_tag = {
            "timestamp": now,
            "first_seen": now,
            "device": device,
            **tag,
            "gtin": gtin,
            "chip": chip_name,
            "count": 1,
        }

        self._tags[tag[self.unique_identifier]] = stored_tag
        self._index_add(tag[self.unique_identifier], stored_tag)

        return stored_tag

    def _existing_tag(self, tag: Dict[str, Any], device: str) -> Dict[str, Any]:
        """
        Update an existing tag.

        Args:
            tag: Incoming tag data.
            device: Source device identifier.
        Returns:
            The updated stored tag.
        """
        current = self._tags[tag[self.unique_identifier]]
        primary_key = tag[self.unique_identifier]

        old_epc = current.get("epc")

        current["count"] += 1
        current["timestamp"] = datetime.now()

        current["rssi"] = tag.get("rssi")
        current["ant"] = tag.get("ant")
        current["epc_len"] = tag.get("epc_len")
        if not device == current["device"]:
            current["device"] = device
        if not tag.get("epc") == current.get("epc"):
            current["epc"] = tag.get("epc")
            try:
                gtin = SGTIN.decode(tag.get("epc")).gtin
            except Exception:
                gtin = None
            current["gtin"] = gtin
        if not tag.get("protected") == current.get("protected"):
            current["protected"] = tag.get("protected")

        self._index_move("epc", primary_key, old_epc, current.get("epc"))

        return current

    def get_all(self, limit: int | None = None) -> list[Dict[str, Any]]:
        """
        Retrieve all stored tags.

        Returns:
            A list of tag dictionaries.
        """
        if limit is not None and limit < 0:
            limit = None
        with self._lock:
            return list(islice(self._tags.values(), limit))

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

        with self._lock:
            if self.unique_identifier == identifier_type:
                return self._tags.get(identifier_value)

            primary_key = self._index[identifier_type].get(identifier_value)
            if primary_key is None:
                return None
            return self._tags.get(primary_key)

    def clear(self) -> None:
        """
        Remove all stored tags.
        """
        with self._lock:
            self._index["epc"].clear()
            self._index["tid"].clear()
            self._tags.clear()

    def get_tid_from_epc(self, epc: str) -> Optional[str]:
        """
        Retrieve the TID associated with a given EPC.

        Args:
            epc: EPC value.

        Returns:
            The TID if found, otherwise None.
        """
        with self._lock:
            if self.unique_identifier == "epc":
                tag = self._tags.get(epc)
            else:
                primary_key = self._index["epc"].get(epc)
                if primary_key is None:
                    return None
                tag = self._tags.get(primary_key)
            if tag:
                return tag.get("tid")
            return None

    def get_epcs(self, limit: int | None = None) -> list[str]:
        """
        Retrieve a list of all stored EPCs.

        Returns:
            A list of EPC strings.
        """
        if limit is not None and limit < 0:
            limit = None
        with self._lock:
            return list(islice((tag.get("epc") for tag in self._tags.values()), limit))

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

    ### REMOVE
    def _remove_where(self, predicate: Callable[[Dict[str, Any]], bool]) -> list[Dict[str, Any]]:
        """
        Remove tags that match a predicate using a single pass.

        This method expects the caller to hold the lock.
        """
        removed_tags: list[Dict[str, Any]] = []
        keys_to_remove: list[str] = []

        for key, tag in self._tags.items():
            if predicate(tag):
                removed_tags.append(tag)
                keys_to_remove.append(key)

        for key in keys_to_remove:
            removed = self._tags.pop(key, None)
            if removed is not None:
                self._index_remove(key, removed)

        return removed_tags

    def remove_tag_by_identifier(self, identifier_value: str, identifier_type: str = "epc") -> list[Dict[str, Any]]:
        """
        Remove a tag by its identifier.

        Args:
            identifier_value: The value of the identifier (EPC or TID).
            identifier_type: The type of identifier ("epc" or "tid").

        Returns:
            A list with all removed tags.
        """
        if identifier_type not in ("epc", "tid"):
            identifier_type = "epc"

        removed_tags: list[Dict[str, Any]] = []

        with self._lock:
            if self.unique_identifier == identifier_type:
                removed_tag = self._tags.pop(identifier_value, None)
                if removed_tag is not None:
                    self._index_remove(identifier_value, removed_tag)
                    removed_tags.append(removed_tag)
                return removed_tags

            return self._remove_where(lambda tag: tag.get(identifier_type) == identifier_value)

    def remove_tags_before_timestamp(self, timestamp: datetime) -> list[Dict[str, Any]]:
        """
        Remove tags older than a given timestamp.

        Args:
            timestamp: Minimum timestamp to keep.

        Returns:
            A list with all removed tags.
        """
        with self._lock:
            return self._remove_where(lambda tag: not tag.get("timestamp") or tag["timestamp"] < timestamp)

    def remove_tags_by_device(self, device: str) -> list[Dict[str, Any]]:
        """
        Remove all tags associated with a specific device.

        Args:
            device: Device identifier.

        Returns:
            A list with all removed tags.
        """
        with self._lock:
            return self._remove_where(lambda tag: tag.get("device") == device)
