"""
Exemplo interativo para o cliente OnClick.
Ao iniciar, pede `base_url` e `token`, depois entra em loop de comandos.
"""

import json
import asyncio
from smartx_rfid.clients.on_click import OnClickClient


def _print_menu() -> None:
    print()
    print("Escolha a função a executar:")
    print("  1 - Health check")
    print("  2 - Obter pedido por ID")
    print("  3 - Obter produto por ID")
    print("  4 - Atualizar status do pedido")
    print("  q - Sair")
    print()


def _pretty_print(obj) -> None:
    try:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception:
        print(obj)


async def main() -> None:
    print("Exemplo interativo do OnClick")
    base_url = input("Base URL: ").strip()
    token = input("Token: ").strip()

    client = OnClickClient(base_url=base_url, token=token)

    while True:
        _print_menu()
        choice = input("> ").strip().lower()
        if choice in ("q", "quit", "sair", "exit"):
            print("Saindo.")
            break

        if choice == "1":
            print("Executando health_check...")
            try:
                ok = await client.health_check()
                print("Resultado:", "OK" if ok else "Falhou")
            except Exception as exc:
                print("Erro:", exc)

        elif choice == "2":
            order_id = input("ID do pedido: ").strip()
            if not order_id:
                print("ID vazio, tente novamente.")
                continue
            try:
                data = await client.get_order(order_id)
                _pretty_print(data)
            except Exception as exc:
                print("Erro ao obter pedido:", exc)

        elif choice == "3":
            product_id = input("ID do produto: ").strip()
            if not product_id:
                print("ID vazio, tente novamente.")
                continue
            try:
                data = await client.get_product(product_id)
                _pretty_print(data)
            except Exception as exc:
                print("Erro ao obter produto:", exc)

        elif choice == "4":
            order_id = input("ID do pedido: ").strip()
            if not order_id:
                print("ID vazio, tente novamente.")
                continue
            status = input("Novo status do pedido (número): ").strip()
            if not status.isdigit():
                print("Status inválido, deve ser um número.")
                continue
            try:
                ok = await client.update_order_status(order_id, int(status))
                print("Resultado:", "OK" if ok else "Falhou")
            except Exception as exc:
                print("Erro ao atualizar status do pedido:", exc)
        else:
            print("Opção inválida. Digite 1, 2, 3, 4 ou q para sair.")


if __name__ == "__main__":
    asyncio.run(main())
