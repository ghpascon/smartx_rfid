import sys
import tempfile
from pathlib import Path

from smartx_rfid.utils.path import get_frozen_path


def test_get_frozen_path_source(monkeypatch):
    # Simula ambiente não frozen
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    # O arquivo de teste está dentro do projeto, então deve resolver para a raiz
    result = get_frozen_path("README.md")
    assert result.exists(), f"Arquivo não encontrado: {result}"
    assert result.name == "README.md"


def test_get_frozen_path_frozen(monkeypatch):
    # Simula ambiente frozen
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", tmpdir, raising=False)
        # Cria um arquivo fake dentro do _MEIPASS
        fake_file = Path(tmpdir) / "fake.txt"
        fake_file.write_text("conteudo")
        result = get_frozen_path("fake.txt")
        assert result.exists(), f"Arquivo não encontrado no frozen: {result}"
        assert result.read_text() == "conteudo"
