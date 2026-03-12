import pytest

from smartx_rfid.utils.printer import generate_zpl_with_params


class TestPrinter:
    def test_generate_zpl_with_params(self):
        zpl_template = "^XA^FO50,50^A0N,40,40^FD{epc}^FS^XZ"
        params = {"epc": "000000000000000000000001"}
        expected_zpl = "^XA^FO50,50^A0N,40,40^FD000000000000000000000001^FS^XZ"

        generated_zpl = generate_zpl_with_params(zpl_template, **params)
        assert generated_zpl == expected_zpl

    def test_generate_zpl_with_missing_param(self):
        zpl_template = "^XA^FO50,50^A0N,40,40^FD{epc}^FS^XZ"
        params = {}  # Missing 'epc' parameter
        success = False
        try:
            generate_zpl_with_params(zpl_template, **params)
            success = True
        except ValueError:
            pass
        assert not success


if __name__ == "__main__":
    pytest.main([__file__])
