from smartx_rfid.utils import TagList
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    tags = TagList()
    tags.add({"epc": "1234"})
    tags.add({"epc": "12345678"})
    tags.add({"epc": "000000000000000000000001"})
    for tag in tags.get_all():
        logging.info(f"EPC: {tag.get('epc')}, EPC Length: {tag.get('epc_len')}")
