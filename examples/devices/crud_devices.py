"""
Exemplo de operações CRUD no DeviceManager
===========================================

Demonstra como criar, atualizar e deletar configurações de dispositivos em
tempo de execução. Após cada operação o DeviceManager recarrega automaticamente
a lista de dispositivos.

Execute a partir da raiz do projeto:
    python examples/devices/crud_devices.py
"""

import asyncio
import json
import logging
import tempfile

from smartx_rfid.devices import DeviceManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Configs de exemplo que serão criadas / atualizadas no diretório temporário
# ---------------------------------------------------------------------------

TCP_DEVICE = {
    "READER": "TCP",
    "IP": "192.168.1.200",
    "PORT": 23,
}

TCP_DEVICE_UPDATED = {
    "READER": "TCP",
    "IP": "10.0.0.50",
    "PORT": 9090,
}

SERIAL_DEVICE = {
    "READER": "SERIAL",
    "PORT": "AUTO",
    "BAUDRATE": 9600,
    "VID": 259,
    "PID": 24673,
}


async def main():
    # Usamos um diretório temporário para não poluir o diretório real de devices.
    # Em produção, passe o caminho real, p.ex. DeviceManager(devices_path="/data/devices")
    with tempfile.TemporaryDirectory() as tmp_dir:
        manager = DeviceManager(devices_path=tmp_dir)

        print("\n" + "=" * 60)
        print("1. Listando devices iniciais (deve estar vazio)")
        print("=" * 60)
        manager.load_devices()
        print(f"  Devices carregados: {manager.get_devices()}")

        # ------------------------------------------------------------------
        # CREATE
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("2. Criando device 'leitor_tcp'")
        print("=" * 60)
        ok, err = manager.create_device_config("leitor_tcp", TCP_DEVICE)
        print(f"  Resultado: ok={ok}, err={err}")
        print(f"  Devices após create: {manager.get_devices()}")

        print("\n  Criando device 'leitor_serial'")
        ok, err = manager.create_device_config("leitor_serial", SERIAL_DEVICE)
        print(f"  Resultado: ok={ok}, err={err}")
        print(f"  Devices após create: {manager.get_devices()}")

        print("\n  Tentando criar 'leitor_tcp' novamente sem overwrite (deve falhar)")
        ok, err = manager.create_device_config("leitor_tcp", TCP_DEVICE)
        print(f"  Resultado: ok={ok}, err={err}")

        # ------------------------------------------------------------------
        # READ (já existente)
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("3. Lendo configuração de 'leitor_tcp'")
        print("=" * 60)
        config = manager.get_device_config("leitor_tcp")
        print(f"  Config: {json.dumps(config, indent=4)}")

        print("\n  Lendo info de todos os devices")
        for info in manager.get_device_info():
            print(f"  {info}")

        # ------------------------------------------------------------------
        # UPDATE
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("4. Atualizando 'leitor_tcp' com novo IP/porta")
        print("=" * 60)
        ok, err = await manager.update_device_config("leitor_tcp", TCP_DEVICE_UPDATED)
        print(f"  Resultado: ok={ok}, err={err}")
        config = manager.get_device_config("leitor_tcp")
        print(f"  Config após update: {json.dumps(config, indent=4)}")

        # ------------------------------------------------------------------
        # DELETE
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("5. Deletando 'leitor_serial'")
        print("=" * 60)
        print(f"  Devices antes do delete: {manager.get_devices()}")
        ok, err = await manager.delete_device_config("leitor_serial")
        print(f"  Resultado: ok={ok}, err={err}")
        print(f"  Devices após delete: {manager.get_devices()}")

        print("\n  Tentando deletar device inexistente (deve falhar)")
        ok, err = await manager.delete_device_config("nao_existe")
        print(f"  Resultado: ok={ok}, err={err}")

        # ------------------------------------------------------------------
        # Validação de config inválida
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("6. Tentando criar device sem campo 'reader' (deve falhar)")
        print("=" * 60)
        ok, err = manager.create_device_config("invalido", {"IP": "1.2.3.4"})
        print(f"  Resultado: ok={ok}, err={err}")

        print("\n" + "=" * 60)
        print("Concluído!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
