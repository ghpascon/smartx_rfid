import logging

from smartx_rfid.clients.id_logistic import IdLogisticClient


logging.basicConfig(level=logging.INFO)


def test_compare_gtins_support_data_supconf():
    client = IdLogisticClient()

    support_supconf = [
        {
            "pedido": "P1",
            "suporte": "A1",
            "sku": "S1",
            "descricao": "desc1",
            "ean": "123",
            "quantidade": 2,
            "posicao": None,
        },
        {
            "pedido": "P2",
            "suporte": "A1",
            "sku": "S2",
            "descricao": "desc2",
            "ean": "456",
            "quantidade": 1,
            "posicao": None,
        },
    ]
    current_gtins_sup = {"123": 1, "789": 3}

    res_sup = client.compare_gtins_support_data(support_supconf, current_gtins_sup.copy())
    by_ean = {r["ean"]: r for r in res_sup}

    assert by_ean["123"]["status"] == "FAL" and by_ean["123"]["sinal"] == "<"
    assert by_ean["456"]["status"] == "FAL" and by_ean["456"]["sinal"] == "<"
    assert by_ean["789"]["status"] == "INV" and by_ean["789"]["sinal"] == "!"
    assert by_ean["789"].get("descricao") == "NAO_ESPERADO"


def test_compare_gtins_support_data_viewestoq():
    client = IdLogisticClient()

    support_view = [
        {"ean": "ABC", "codpro": "P1", "ds1pro": "X", "qtd_total": 5},
        {"ean": "DEF", "codpro": "P2", "ds1pro": "Y", "qtd_total": 0},
    ]
    current_gtins_view = {"ABC": 5, "XYZ": 1}

    res_view = client.compare_gtins_support_data(support_view, current_gtins_view.copy())
    by_ean_view = {r["ean"]: r for r in res_view}

    assert by_ean_view["ABC"]["status"] == "OK" and by_ean_view["ABC"]["sinal"] == "="
    assert by_ean_view["DEF"]["status"] == "OK" and by_ean_view["DEF"]["sinal"] == "="
    assert by_ean_view["XYZ"]["status"] == "INV" and by_ean_view["XYZ"]["sinal"] == "!"


def test_compare_gtins_static():
    client = IdLogisticClient()

    current_gtins = {
        "123": 5,
        "456": 3,
        "789": 2,
    }
    expected_gtins = {
        "123": 5,
        "456": 5,
        "789": 1,
    }

    comp = client.compare_gtins(expected_gtins.copy(), current_gtins.copy())
    by_gtin = {r["gtin"]: r for r in comp}

    assert by_gtin["123"]["status"] == "OK" and by_gtin["123"]["sinal"] == "="
    assert by_gtin["456"]["status"] == "FAL" and by_gtin["456"]["sinal"] == "<"
    assert by_gtin["789"]["status"] == "SOB" and by_gtin["789"]["sinal"] == ">"


def test_compare_gtins_with_semicolon_and_comma():
    client = IdLogisticClient()

    current_gtins = {
        "123": 5,
        "456": 3,
        "789": 1,
        "000": 2,
    }
    # expected uses semicolon and comma as delimiters
    expected_gtins = {
        "123;456": 8,
        "789,000": 3,
    }

    comp = client.compare_gtins(expected_gtins.copy(), current_gtins.copy())
    by_gtin = {r["gtin"]: r for r in comp}

    assert by_gtin["123;456"]["status"] == "OK" and by_gtin["123;456"]["sinal"] == "="
    assert by_gtin["789,000"]["status"] == "OK" and by_gtin["789,000"]["sinal"] == "="
    # no unexpected items should remain (all keys used)
    inv_items = [r for r in comp if r["status"] == "INV"]
    assert len(inv_items) == 0


def test_compare_gtins_support_data_with_delimiters():
    client = IdLogisticClient()

    support_data = [
        {"ean": "123;456", "quantidade": 8, "descricao": "group1"},
        {"ean": "789,000", "quantidade": 3, "descricao": "group2"},
    ]
    current_gtins = {"123": 5, "456": 3, "789": 1, "000": 2, "X": 4}

    res = client.compare_gtins_support_data(support_data, current_gtins.copy())
    by_ean = {r["ean"]: r for r in res}

    assert by_ean["123;456"]["status"] == "OK" and by_ean["123;456"]["sinal"] == "="
    assert by_ean["789,000"]["status"] == "OK" and by_ean["789,000"]["sinal"] == "="
    # unexpected item X should be present
    inv = [r for r in res if r["status"] == "INV"]
    assert len(inv) == 1 and inv[0]["ean"] == "X"
