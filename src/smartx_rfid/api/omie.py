import logging
import httpx


class ApiOmie:
    def __init__(self, app_key: str, app_secret: str, base_url: str = "https://app.omie.com.br/api/v1/geral/"):
        logging.info("[OMIE] Initializing ApiOmie")
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url
        self.client = httpx.Client(timeout=5.0)

    def _call_api(self, endpoint: str, payload: dict):
        """Internal call to Omie API"""
        url = f"{self.base_url}{endpoint}/"
        body = {"app_key": self.app_key, "app_secret": self.app_secret, **payload}
        headers = {"Content-Type": "application/json"}
        logging.debug(f"[OMIE] Calling {url} with payload: {payload}")
        response = self.client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_all_products(self, per_page: int = 100):
        """List all products/services, paginated automatically"""
        all_products = []
        page = 1
        while True:
            payload = {
                "call": "ListarProdutos",
                "param": [
                    {
                        "pagina": page,
                        "registros_por_pagina": per_page,
                        "apenas_importado_api": "N",
                        "filtrar_apenas_omiepdv": "N",
                    }
                ],
            }
            data = self._call_api("produtos", payload)
            products = data.get("produto_servico_cadastro", [])
            all_products.extend(
                [
                    {
                        "codigo": p.get("codigo"),
                        "descricao": p.get("descricao"),
                    }
                    for p in products
                ]
            )

            logging.info(f"[OMIE] Page {page}: {len(products)} products fetched")

            # Stop if there are no more products
            if len(products) < per_page:
                break
            page += 1
        return all_products

    def get_all_clients(self, per_page: int = 100):
        """List all clients, paginated automatically"""
        all_clients = []
        page = 1
        while True:
            payload = {"call": "ListarClientes", "param": [{"pagina": page, "registros_por_pagina": per_page}]}
            data = self._call_api("clientes", payload)
            clients = data.get("clientes_cadastro", [])
            all_clients.extend([c.get("razao_social") for c in clients if c.get("razao_social") is not None])

            logging.info(f"[OMIE] Page {page}: {len(clients)} clients fetched")

            # Stop if there are no more clients
            if len(clients) < per_page:
                break
            page += 1
        return all_clients
