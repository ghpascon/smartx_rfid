import logging
import httpx
import asyncio
from typing import Dict, List, Tuple


class ApiOmie:
    def __init__(self, app_key: str, app_secret: str, base_url: str = "https://app.omie.com.br/api/v1/"):
        logging.info("[OMIE] Initializing ApiOmie")
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url

    async def _call_api(self, client: httpx.AsyncClient, endpoint: str, payload: dict) -> Tuple[bool, dict]:
        """Internal async call to Omie API"""
        try:
            url = f"{self.base_url}{endpoint}/"
            body = {"app_key": self.app_key, "app_secret": self.app_secret, **payload}
            headers = {"Content-Type": "application/json"}
            logging.debug(f"[OMIE] Calling {url}")
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            return True, response.json()
        except httpx.HTTPStatusError as e:
            logging.error(f"[OMIE] API call failed: {e.response.status_code} - {e.response.text}")
            return False, {"error": f"HTTP error: {e.response.status_code}", "detail": e.response.text}
        except Exception as e:
            logging.error(f"[OMIE] API call exception: {e}")
            return False, {"error": "Request failed", "detail": str(e)}

    async def _fetch_all_products(self, client: httpx.AsyncClient) -> Dict[str, dict]:
        """Fetch all products and return as dict indexed by codigo"""
        products_dict = {}
        page = 1
        per_page = 100

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
            success, data = await self._call_api(client, "geral/produtos", payload)
            if not success:
                logging.error(f"[OMIE] Failed to fetch products: {data}")
                break

            products = data.get("produto_servico_cadastro", [])
            for product in products:
                codigo = product.get("codigo")
                if codigo:
                    products_dict[codigo] = {
                        "codigo": codigo,
                        "descricao": product.get("descricao"),
                        "familia": product.get("descricao_familia"),
                    }

            logging.info(f"[OMIE] Products page {page}: {len(products)} fetched")
            if len(products) < per_page:
                break
            page += 1

        logging.info(f"[OMIE] Total products: {len(products_dict)}")
        return products_dict

    async def _fetch_all_clients(self, client: httpx.AsyncClient) -> Dict[str, dict]:
        """Fetch all clients and return as dict indexed by codigo"""
        clients_dict = {}
        page = 1
        per_page = 100

        while True:
            payload = {"call": "ListarClientes", "param": [{"pagina": page, "registros_por_pagina": per_page}]}
            success, data = await self._call_api(client, "geral/clientes", payload)
            if not success:
                logging.error(f"[OMIE] Failed to fetch clients: {data}")
                break
            clients = data.get("clientes_cadastro", [])
            for client_data in clients:
                codigo = client_data.get("codigo_cliente_omie")
                if codigo and client_data.get("razao_social"):
                    clients_dict[codigo] = {
                        "codigo": codigo,
                        "nome": client_data.get("razao_social"),
                        "cnpj": client_data.get("cnpj_cpf"),
                    }

            logging.info(f"[OMIE] Clients page {page}: {len(clients)} fetched")
            if len(clients) < per_page:
                break
            page += 1

        logging.info(f"[OMIE] Total clients: {len(clients_dict)}")
        return clients_dict

    async def _fetch_all_orders_raw(
        self, client: httpx.AsyncClient, filters: dict | None = None, raw_order: bool = False
    ) -> List[dict]:
        """Fetch all orders and return raw order items with client codes"""
        all_orders = []
        page = 1
        per_page = 100
        has_errors = False

        while True:
            if filters is None:
                filters = {}
            payload = {
                "call": "ListarPedidos",
                "param": [{"pagina": page, "registros_por_pagina": per_page, "apenas_importado_api": "N", **filters}],
            }
            success, data = await self._call_api(client, "produtos/pedido", payload)

            if not success:
                logging.error(f"[OMIE] Failed to fetch orders: {data}")
                has_errors = True
                break

            orders = data.get("pedido_venda_produto", [])
            page_orders = []

            for order in orders:
                if raw_order:
                    page_orders.append(order)
                    continue
                try:
                    cabecalho = order.get("cabecalho", {})
                    etapa = int(cabecalho.get("etapa", 0))
                    if etapa < 20:
                        continue

                    produtos = order.get("det", [])
                    numero_pedido = cabecalho.get("numero_pedido")
                    codigo_cliente = cabecalho.get("codigo_cliente")

                    if not produtos:
                        continue

                    for produto_data in produtos:
                        try:
                            produto = produto_data.get("produto", {})
                            codigo = produto.get("codigo")
                            qtd = produto.get("quantidade", 1)
                            if codigo:
                                try:
                                    qtd_int = int(float(qtd))
                                except Exception:
                                    qtd_int = 1
                                for _ in range(qtd_int):
                                    page_orders.append(
                                        {
                                            "numero_pedido": int(numero_pedido),
                                            "codigo_cliente": codigo_cliente,  # Será substituído depois
                                            "codigo_produto": codigo,  # Será enriquecido depois
                                            "etapa": etapa,
                                        }
                                    )
                        except Exception as e:
                            logging.error(f"[OMIE] Erro ao processar produto do pedido {numero_pedido}: {e}")
                            has_errors = True

                except Exception as e:
                    logging.error(f"[OMIE] Erro ao processar pedido: {e}")
                    has_errors = True

            all_orders.extend(page_orders)
            logging.info(f"[OMIE] Orders page {page}: {len(page_orders)} items fetched")

            if len(orders) < per_page:
                break
            page += 1

        logging.info(f"[OMIE] Total raw orders: {len(all_orders)}, has_errors: {has_errors}")
        return all_orders

    def _enrich_orders(
        self, raw_orders: List[dict], clients_dict: Dict[str, dict], products_dict: Dict[str, dict]
    ) -> List[dict]:
        """Enrich orders with client names and product descriptions"""
        enriched_orders = []

        for order in raw_orders:
            # Get client info
            client = clients_dict.get(order["codigo_cliente"], {})
            # Get product info
            product = products_dict.get(order["codigo_produto"], {})
            product_code = order.get("codigo_produto")
            if not product_code:
                continue
            product_code = product_code.lower()
            if not product_code.startswith("smtx") or product_code[4:5].isdigit():
                continue

            enriched_order = {
                "numero_pedido": order.get("numero_pedido"),
                "etapa": order.get("etapa"),
                "nome_cliente": client.get("nome"),
                "cnpj_cliente": client.get("cnpj"),
                "codigo_produto": order.get("codigo_produto"),
                "descricao_produto": product.get("descricao"),
                "familia_produto": product.get("familia", ""),
            }
            enriched_orders.append(enriched_order)

        return enriched_orders

    async def get_all_orders(self, per_page: int = 100) -> dict:
        """Fetch all orders with parallel API calls and data enrichment"""
        timeout = httpx.Timeout(30.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            logging.info("[OMIE] Starting parallel API calls...")

            # Execute all API calls in parallel
            products_task = self._fetch_all_products(client)
            clients_task = self._fetch_all_clients(client)
            orders_task = self._fetch_all_orders_raw(client)

            # Wait for all tasks to complete
            products_dict, clients_dict, raw_orders = await asyncio.gather(
                products_task, clients_task, orders_task, return_exceptions=True
            )

            # Check for exceptions
            if isinstance(products_dict, Exception):
                logging.error(f"[OMIE] Products fetch failed: {products_dict}")
                products_dict = {}
            if isinstance(clients_dict, Exception):
                logging.error(f"[OMIE] Clients fetch failed: {clients_dict}")
                clients_dict = {}
            if isinstance(raw_orders, Exception):
                logging.error(f"[OMIE] Orders fetch failed: {raw_orders}")
                return {"success": False, "error": str(raw_orders)}

            # Enrich orders with client and product data
            logging.info("[OMIE] Enriching orders with client and product data...")
            enriched_orders = self._enrich_orders(raw_orders, clients_dict, products_dict)

            total_items = len(enriched_orders)
            logging.info(f"[OMIE] Process completed: {total_items} enriched orders")

            return {
                "success": True,
                "total_items": total_items,
                "orders": enriched_orders,
            }

    async def get_orders_filtered(self, filters: dict) -> dict:
        timeout = httpx.Timeout(30.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            orders = await self._fetch_all_orders_raw(client, filters=filters, raw_order=True)
            return orders

    async def get_order_by_number(self, order_number: int) -> dict:
        filters = {
            "numero_pedido_de": order_number,
            "numero_pedido_ate": order_number,
        }
        try:
            orders = await self.get_orders_filtered(filters)
            return True, orders[0] if orders else None
        except Exception as e:
            logging.error(f"[OMIE] Failed to fetch order by number {order_number}: {e}")
            return False, {"error": str(e)}

    async def get_order(self, order_number: int) -> dict:
        # Consultar
        payload = {
            "call": "ConsultarPedido",
            "param": [
                {
                    "numero_pedido": str(order_number),
                }
            ],
        }
        success, order_data = await self._call_api(httpx.AsyncClient(), "produtos/pedido", payload)
        if not success:
            logging.error(f"[OMIE] Failed to fetch order {order_number} for updating: {order_data}")
            return False, order_data
        return True, order_data

    async def get_order_data(self, order_number: int) -> dict:
        success, order_data = await self.get_order(order_number)
        if not success:
            logging.error(f"[OMIE] Failed to get cod_order for order {order_number}: {order_data}")
            return False, order_data
        cod_order = order_data.get("pedido_venda_produto", {}).get("cabecalho", {}).get("codigo_pedido")
        etapa = order_data.get("pedido_venda_produto", {}).get("cabecalho", {}).get("etapa")
        can_update = etapa and int(etapa) >= 20 and int(etapa) < 60
        if not cod_order or not etapa:
            logging.error(f"[OMIE] cod_order not found for order {order_number}")
            return False, {"error": "cod_order not found"}
        dets = order_data.get("pedido_venda_produto", {}).get("det", [])
        product_codes = []
        for p in dets:
            prod = p.get("produto", {})
            codigo = prod.get("codigo")
            qtd = prod.get("quantidade", 1)
            if codigo:
                try:
                    qtd_int = int(float(qtd))
                except Exception:
                    qtd_int = 1
                product_codes.extend([codigo] * qtd_int)
        return True, {
            "cod_order": cod_order,
            "can_update": can_update,
            "product_codes": product_codes,
        }

    async def add_serial_to_nf(self, cod_order: int, extra_data: str) -> dict:
        # Alterar
        payload = {
            "call": "AlterarPedidoVenda",
            "param": [
                {
                    "cabecalho": {
                        "codigo_pedido": cod_order,
                    },
                    "informacoes_adicionais": {"dados_adicionais_nf": extra_data},
                }
            ],
        }

        success, response = await self._call_api(httpx.AsyncClient(), "produtos/pedido", payload)
        if not success:
            logging.error(f"[OMIE] Failed to update order {cod_order} with extra data: {response}")
            return False, response
        logging.info(f"[OMIE] Successfully added extra fiscal data to order {cod_order}")
        return True, response
