import httpx
from typing import Optional
from smartx_rfid.parser.main import get_serial_from_tid
from smartx_rfid.utils import regex_hex


class OnClickClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    # Basic methods for interacting with the OnClick API
    async def health_check(self) -> bool:
        url = f"{self.base_url}/"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.status_code == 200

    async def get_order(self, order_id: str) -> Optional[dict]:
        url = f"{self.base_url}/pedido?nrpedido={order_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    async def get_product_by_auxiliar_code(self, auxiliar_code: str) -> Optional[dict]:
        url = f"{self.base_url}/produto/codauxiliar/{auxiliar_code}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    async def get_product(self, product_id: str) -> Optional[dict]:
        url = f"{self.base_url}/produto/{product_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    # enhancements for better usability
    async def get_enhanced_order(self, order_id: str) -> Optional[dict]:
        order = await self.get_order(order_id)
        if order is None:
            return None

        expected_products = []
        for product in order.get("iped", []):
            expected_products.append(
                {
                    "product_code": product.get("codprod"),
                    "description": product.get("descricao"),
                    "qty": product.get("qtde"),
                }
            )

        # Simplify the order data structure
        simplified_order = {
            "id": str(order.get("nrpedido")),
            "name": order.get("nome"),
            "date": order.get("dtpedido"),
            "expected_products": expected_products,
        }
        return simplified_order

    # serialization methods
    @staticmethod
    def serialize_tag(product_code: str, tid: str) -> str:
        """
        Serialize product code and TID into a single string.
        Format: {product_code}:{tid}
        """
        if not product_code or not tid:
            raise ValueError("Product code and TID must be provided.")
        if not regex_hex(tid, 24):
            raise ValueError("TID must be a valid 24-character hexadecimal string.")
        serial = get_serial_from_tid(tid)
        if serial is None:
            raise ValueError("Invalid TID format; unable to extract serial number.")
        return f"{(str(product_code)).zfill(12)}{serial.zfill(12)}"  # Ensure both parts are 12 characters long

    @staticmethod
    def deserialize_tag(serialized: str) -> Optional[dict]:
        """
        Deserialize a serialized tag string into its components.
        Expected format: {product_code}{serial}
        """
        if not serialized or len(serialized) != 24:
            return None
        product_code = serialized[:12].lstrip("0")  # Remove leading zeros
        serial = serialized[12:].lstrip("0")  # Remove leading zeros
        return {"product_code": product_code, "serial": serial}
