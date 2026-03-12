import hashlib


def get_hash(data: str) -> str:
    return str(hashlib.sha256(data.encode("utf-8")).hexdigest())
