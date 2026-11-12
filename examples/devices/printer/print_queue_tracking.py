"""Enfileira etiquetas e correlaciona cada impressão com o EPC e seu resultado."""

import asyncio

from smartx_rfid.devices.printer import SatoPrinter, simple_zpl_example


printer = SatoPrinter(ip="192.168.1.112", name="SATO-EXPEDICAO")
# Mantém os dados de negócio associados ao ID retornado pela fila.
print_jobs: dict[str, dict[str, str]] = {}


def on_event(device: dict, event_type: str, event_data=None):
    if event_type == "print_sent":
        print(f"Enviado à impressora: ID={event_data}")
    elif event_type in {"print_success", "print_error"}:
        job = print_jobs.get(event_data, {})
        outcome = "IMPRESSO" if event_type == "print_success" else "ERRO NA IMPRESSÃO"
        print(f"{outcome}: ID={event_data}, EPC={job.get('epc', 'desconhecido')}")
    elif event_type == "print_sent_error":
        print_id = event_data.get("id") if isinstance(event_data, dict) else None
        job = print_jobs.get(print_id, {})
        error = event_data.get("error") if isinstance(event_data, dict) else event_data
        print(f"FALHA AO ENVIAR: ID={print_id}, EPC={job.get('epc', 'desconhecido')}, erro={error}")
    elif event_type == "status":
        print(f"{device.get('name')}: {event_data}")


def build_label(epc: str) -> str:
    return simple_zpl_example.replace("000000000000000000000001", epc)


async def main():
    labels = [
        {"epc": "000000000000000000000101", "zpl": build_label("000000000000000000000101")},
        {"epc": "000000000000000000000102", "zpl": build_label("000000000000000000000102")},
    ]

    # Para um item, add_to_print_queue retorna um ID (str); para uma lista, retorna list[str].
    print_ids = printer.add_to_print_queue([label["zpl"] for label in labels])
    assert isinstance(print_ids, list)
    for print_id, label in zip(print_ids, labels):
        print_jobs[print_id] = label
        print(f"Na fila: ID={print_id}, EPC={label['epc']}")

    # O callback correlaciona print_success / print_error com o ID acima.
    printer.on_event = on_event
    await printer.connect()


if __name__ == "__main__":
    asyncio.run(main())
