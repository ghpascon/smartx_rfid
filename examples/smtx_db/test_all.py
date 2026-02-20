"""
Interactive test for all SmtxDb methods.
Run directly: python examples/smtx_db/test_all.py
"""

import json
import logging
import sys
from smartx_rfid.smtx_db.main import SmtxDb, ProductsOrders, ProductsType, ReadersType, Readers

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def p(label: str, value):
    print(f"  {label}: {json.dumps(value, indent=4, default=str)}")


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def ok(success: bool, detail=None):
    status = "OK" if success else "FAIL"
    detail_str = f" -> {detail}" if detail is not None else ""
    print(f"  [{status}]{detail_str}")
    return success


# ─────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────
section("CONNECTION")
default_conn = "mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx_teste"
conn = input(f"  Connection string [{default_conn}]: ").strip() or default_conn

try:
    db = SmtxDb(conn)
    db.db_manager.register_models(ProductsType, ReadersType, Readers, ProductsOrders)
    db.db_manager.create_tables()  # Ensure tables exist for testing
    print("  Connected.")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────
# CUSTOMERS
# ─────────────────────────────────────────────
section("CUSTOMERS")

print("\n[get_customers(limit=5)]")
customers = db.get_customers(limit=5)
p("customers", customers)

client_id_str = input("\n  Enter a customer ID to test get_customer (or ENTER to skip): ").strip()
if client_id_str:
    client_id = int(client_id_str)
    print(f"\n[get_customer({client_id})]")
    p("customer", db.get_customer(client_id))


# ─────────────────────────────────────────────
# PRODUCT TYPES
# ─────────────────────────────────────────────
section("PRODUCT TYPES")

print("\n[get_product_types]")
p("product_types", db.get_product_types())

pt_name = input("\n  New product type name (or ENTER to skip): ").strip()
pt_id = None
if pt_name:
    pt_desc = input("  Description (optional): ").strip() or None
    print("\n[add_product_type]")
    success, pt_id = db.add_product_type(pt_name, pt_desc)
    ok(success, f"id={pt_id}")

    if success and pt_id:
        print(f"\n[get_product_type({pt_id})]")
        p("product_type", db.get_product_type(pt_id))

        print(f"\n[update_product_type({pt_id})]")
        ok(*db.update_product_type(pt_id, name=pt_name + " (updated)"))

        print(f"\n[get_product_type({pt_id}) after update]")
        p("product_type", db.get_product_type(pt_id))


# ─────────────────────────────────────────────
# READER TYPES
# ─────────────────────────────────────────────
section("READER TYPES")

print("\n[get_reader_types]")
p("reader_types", db.get_reader_types())

rt_name = input("\n  New reader type name (or ENTER to skip): ").strip()
rt_id = None
if rt_name:
    rt_desc = input("  Description (optional): ").strip() or None
    print("\n[add_reader_type]")
    success, rt_id = db.add_reader_type(rt_name, rt_desc)
    ok(success, f"id={rt_id}")

    if success and rt_id:
        print(f"\n[get_reader_type({rt_id})]")
        p("reader_type", db.get_reader_type(rt_id))

        print(f"\n[update_reader_type({rt_id})]")
        ok(*db.update_reader_type(rt_id, name=rt_name + " (updated)"))


# ─────────────────────────────────────────────
# READERS
# ─────────────────────────────────────────────
section("READERS")

print("\n[get_readers]")
p("readers", db.get_readers())

print("\n[get_available_readers]")
p("available_readers", db.get_available_readers())

reader_id = None
use_rt_id = rt_id
if use_rt_id is None:
    rt_id_str = input("\n  Enter a reader_type_id to add a reader (or ENTER to skip): ").strip()
    use_rt_id = int(rt_id_str) if rt_id_str else None

if use_rt_id:
    serial = input("  Reader serial number: ").strip()
    hostname = input("  Reader hostname (optional): ").strip() or None
    print("\n[add_reader]")
    success, reader_id = db.add_reader(use_rt_id, serial, hostname)
    ok(success, f"id={reader_id}")

    if success and reader_id:
        print(f"\n[get_reader({reader_id})]")
        p("reader", db.get_reader(reader_id))

        print(f"\n[update_reader({reader_id}, hostname='updated-host')]")
        ok(*db.update_reader(reader_id, hostname="updated-host"))

        print(f"\n[get_reader({reader_id}) after update]")
        p("reader", db.get_reader(reader_id))

# Invalid reader_type_id test
print("\n[add_reader with invalid reader_type_id=99999]")
ok(*db.add_reader(99999, "INVALID-SERIAL"))


# ─────────────────────────────────────────────
# PRODUCT ORDERS
# ─────────────────────────────────────────────
section("PRODUCT ORDERS")

print("\n[get_product_orders]")
p("product_orders", db.get_product_orders())

order_id = None
use_pt_id = pt_id
use_reader_id = reader_id

if use_pt_id is None:
    pt_id_str = input("\n  Enter a product_type_id to add an order (or ENTER to skip): ").strip()
    use_pt_id = int(pt_id_str) if pt_id_str else None

if use_reader_id is None:
    r_id_str = input("  Enter a reader_id to add an order (or ENTER to skip): ").strip()
    use_reader_id = int(r_id_str) if r_id_str else None

if client_id_str is None or not client_id_str:
    c_id_str = input("  Enter a client_id (customer ID) to add an order (or ENTER to skip): ").strip()
    use_client_id = int(c_id_str) if c_id_str else None
else:
    use_client_id = int(client_id_str)

if use_pt_id and use_client_id and use_reader_id:
    version = input("  Version (e.g. 1.0.0): ").strip() or "1.0.0"
    print("\n[add_product_order]")
    success, order_id = db.add_product_order(use_pt_id, use_client_id, use_reader_id, version)
    ok(success, f"id={order_id}")

    # Reader should now be unavailable
    if success and order_id:
        print(f"\n[get_available_readers] (reader {use_reader_id} should be gone)")
        p("available_readers", db.get_available_readers())

        print(f"\n[get_product_order({order_id})]")
        p("product_order", db.get_product_order(order_id))

        print(f"\n[get_product_orders_by_client({use_client_id})]")
        p("orders_by_client", db.get_product_orders_by_client(use_client_id))

        print(f"\n[get_product_orders_by_product_type({use_pt_id})]")
        p("orders_by_product_type", db.get_product_orders_by_product_type(use_pt_id))

        print(f"\n[product_order_mount({order_id})]")
        ok(*db.product_order_mount(order_id))
        print("  Double mount attempt:")
        ok(*db.product_order_mount(order_id))

        print(f"\n[product_order_ship({order_id})]")
        ok(*db.product_order_ship(order_id))
        print("  Double ship attempt:")
        ok(*db.product_order_ship(order_id))

        print(f"\n[product_order_activate({order_id})]")
        ok(*db.product_order_activate(order_id))
        print("  Double activate attempt:")
        ok(*db.product_order_activate(order_id))

        print(f"\n[get_product_order({order_id}) after lifecycle]")
        p("product_order", db.get_product_order(order_id))

    # Invalid order
    print("\n[add_product_order with invalid product_type_id=99999]")
    ok(*db.add_product_order(99999, use_client_id, use_reader_id, "x"))

    print("\n[add_product_order with invalid client_id=99999]")
    ok(*db.add_product_order(use_pt_id, 99999, use_reader_id, "x"))

    if use_reader_id:
        print(f"\n[add_product_order with unavailable reader {use_reader_id}]")
        ok(*db.add_product_order(use_pt_id, use_client_id, use_reader_id, "x"))


# ─────────────────────────────────────────────
# DECODED ORDERS
# ─────────────────────────────────────────────
section("DECODED ORDERS")

print("\n[get_decoded_orders]")
p("decoded_orders", db.get_decoded_orders())


# ─────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────
section("CLEANUP")
do_cleanup = input("\n  Delete all created test data? (y/N): ").strip().lower() == "y"

if do_cleanup:
    if order_id:
        print(f"\n[delete_product_order({order_id})]")
        ok(*db.delete_product_order(order_id))
        print(f"  Reader {use_reader_id} should be available again:")
        p("reader", db.get_reader(use_reader_id))

    if reader_id:
        print(f"\n[delete_reader({reader_id})]")
        ok(*db.delete_reader(reader_id))

    if rt_id:
        print(f"\n[delete_reader_type({rt_id})]")
        ok(*db.delete_reader_type(rt_id))

    if pt_id:
        print(f"\n[delete_product_type({pt_id})]")
        ok(*db.delete_product_type(pt_id))

    print("\n  Cleanup done.")
else:
    print("  Skipped.")

section("DONE")
