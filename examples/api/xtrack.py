#!/usr/bin/env python3
"""Exemplos de uso da classe ApiXtrack.

Execute:
    python3 examples/api/xtrack.py
"""

import asyncio
import sys
import logging

# Garante que o pacote local `src` esteja no path quando executado a partir da raiz do repositório
sys.path.insert(0, "src")

from smartx_rfid.api.xtrack import ApiXtrack, demo_server_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


async def example_test_connection():
    api = ApiXtrack(demo_server_url, timeout=10)
    success, resp = await api.test_connection()
    print("test_connection:", success)
    print(resp)


async def example_list_categories():
    api = ApiXtrack(demo_server_url)
    success, data = await api.get_categories()
    print("get_categories:", success)
    if success:
        for item in data[:10]:
            print(item)
    else:
        print("Erro:", data)


async def example_list_objects(limit: int = 5):
    api = ApiXtrack(demo_server_url)
    success, data = await api.get_objects()
    print("get_objects:", success)
    if success:
        for obj in data[:limit]:
            print(obj)
    else:
        print("Erro:", data)


async def example_move_object(idcode: str, location_id: str):
    api = ApiXtrack(demo_server_url)
    success, data = await api.move_object(idcode, location_id)
    print("move_object:", success)
    print(data)


async def main():
    # Testa conexão e lista alguns recursos
    await example_test_connection()
    await example_list_categories()
    await example_list_objects()

    # Para testar o movimento de objeto, descomente e ajuste os valores abaixo
    # await example_move_object("IDCODE_EXEMPLO", "LOCATION_ID_EXEMPLO")


if __name__ == "__main__":
    asyncio.run(main())
