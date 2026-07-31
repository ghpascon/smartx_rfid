import httpx
from typing import Optional


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
                    "aux_product_code": product.get("produto_codauxiliar"),
                    "barcode": product.get("codbarra"),
                }
            )

        # Simplify the order data structure
        simplified_order = {
            "id": order.get("nrpedido"),
            "name": order.get("nome"),
            "date": order.get("dtpedido"),
            "nfe": order.get("nfe"),
            "expected_products": expected_products,
        }
        return simplified_order
