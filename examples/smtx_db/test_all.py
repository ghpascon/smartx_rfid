"""
Interactive test for all SmtxDb methods.
Run directly: python examples/smtx_db/test_all.py
"""

import json
import logging
import sys
from datetime import datetime
from smartx_rfid.smtx_db.main import SmtxDb
from smartx_rfid.models.orders import ReadersType, Readers, Orders
from smartx_rfid.models.users import Users

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
default_conn = "mysql+pymysql://root:admin@localhost:3306/orders"
conn = input(f"  Connection string [{default_conn}]: ").strip() or default_conn

try:
    db = SmtxDb(conn)
    db.db_manager.register_models(ReadersType, Readers, Orders, Users)
    db.db_manager.create_tables()  # Ensure tables exist for testing
    print("  Connected.")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
section("USERS")

print("\n[get_users]")
users = db.get_users()
p("users", users)

user_id = None
username = input("\n  New username to create (or ENTER to skip): ").strip()
if username:
    password_hash = "hashed_password_123"  # In real app, use proper hashing
    role = input("  Role [user]: ").strip() or "user"
    print("\n[add_user]")
    success, user_id = db.add_user(username, password_hash, role)
    ok(success, f"id={user_id}")

    if success and user_id:
        print(f"\n[get_user({user_id})]")
        p("user", db.get_user(user_id))

        print(f"\n[get_user_by_username('{username}')]")
        p("user_by_username", db.get_user_by_username(username))

        print(f"\n[update_user({user_id})]")
        ok(*db.update_user(user_id, role="admin"))

        print(f"\n[get_user({user_id}) after update]")
        p("user", db.get_user(user_id))

# Test with existing user if available
if users and not user_id:
    user_id = users[0]["id"]
    username = users[0]["username"]


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

# Use existing reader type if available
reader_types = db.get_reader_types()
if reader_types and not rt_id:
    rt_id = reader_types[0]["id"]


# ─────────────────────────────────────────────
# READERS
# ─────────────────────────────────────────────
section("READERS")

print("\n[get_readers]")
p("readers", db.get_readers())

print("\n[get_available_readers]")
p("available_readers", db.get_available_readers())

print("\n[get_decoded_readers]")
p("decoded_readers", db.get_decoded_readers())

reader_id = None
if rt_id:
    serial = input("\n  Reader serial number (or ENTER to skip): ").strip()
    if serial:
        hostname = input("  Reader hostname (optional): ").strip() or None
        print("\n[add_reader]")
        success, reader_id = db.add_reader(rt_id, serial, hostname)
        ok(success, f"id={reader_id}")

        if success and reader_id:
            print(f"\n[get_reader({reader_id})]")
            p("reader", db.get_reader(reader_id))

            print(f"\n[get_reader_by_serial('{serial}')]")
            p("reader_by_serial", db.get_reader_by_serial(serial))

            print(f"\n[update_reader({reader_id}, hostname='updated-host')]")
            ok(*db.update_reader(reader_id, hostname="updated-host"))

            print(f"\n[get_decoded_reader({reader_id})]")
            p("decoded_reader", db.get_decoded_reader(reader_id))

            print(f"\n[get_decoded_readers_by_ids([{reader_id}])]")
            p("decoded_readers_by_ids", db.get_decoded_readers_by_ids([reader_id]))

# Use existing reader if available
readers = db.get_readers()
if readers and not reader_id:
    reader_id = readers[0]["id"]

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
if user_id:
    order_number = int(input("\n  Order number (or ENTER to skip): ").strip() or "0")
    if order_number:
        client_name = input("  Client name: ").strip()
        client_cnpj = input("  Client CNPJ (optional): ").strip() or None
        product_code = input("  Product code: ").strip()
        product_description = input("  Product description (optional): ").strip() or None
        product_family = input("  Product family (optional): ").strip() or None

        print("\n[add_product_order]")
        success, order_id = db.add_product_order(
            order_number=order_number,
            client_name=client_name,
            client_cnpj=client_cnpj,
            product_code=product_code,
            product_description=product_description,
            product_family=product_family,
            reader_id=reader_id,
            created_by=user_id,
        )
        ok(success, f"id={order_id}")

        if success and order_id:
            # Reader should now be unavailable if assigned
            if reader_id:
                print(f"\n[get_available_readers] (reader {reader_id} should be gone)")
                p("available_readers", db.get_available_readers())

            print(f"\n[get_product_order({order_id})]")
            p("product_order", db.get_product_order(order_id))

            # Test filter methods
            print(f"\n[get_product_orders_by_client('{client_name}')]")
            p("orders_by_client", db.get_product_orders_by_client(client_name))

            if client_cnpj:
                print(f"\n[get_product_orders_by_cnpj('{client_cnpj}')]")
                p("orders_by_cnpj", db.get_product_orders_by_cnpj(client_cnpj))

            print(f"\n[get_product_orders_by_product_code('{product_code}')]")
            p("orders_by_product_code", db.get_product_orders_by_product_code(product_code))

            print(f"\n[get_product_orders_by_order_number({order_number})]")
            p("orders_by_number", db.get_product_orders_by_order_number(order_number))

            if reader_id:
                print(f"\n[get_product_orders_by_reader({reader_id})]")
                p("orders_by_reader", db.get_product_orders_by_reader(reader_id))

            # Test date filtering
            print("\n[get_product_orders_by_date] (today)")
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            p("orders_by_date", db.get_product_orders_by_date(today_start, today_end))

            # Test filters with dict
            print("\n[get_product_orders with filters]")
            p("filtered_orders", db.get_product_orders({"client_name": client_name}))

            # Test comments
            print("\n[add_comment_to_product_order]")
            ok(*db.add_comment_to_product_order(order_id, "Test comment", username))

            print("\n[get_product_order after comment]")
            p("order_with_comment", db.get_product_order(order_id))

            # Test reader management
            if reader_id:
                # Remove reader
                print("\n[update_product_order - remove reader]")
                ok(*db.update_product_order(order_id, reader_id=None))

                # Check reader is available again
                print(f"\n[get_available_readers] (reader {reader_id} should be back)")
                p("available_readers", db.get_available_readers())

                # Add reader back
                print("\n[add_reader_to_product_order]")
                ok(*db.add_reader_to_product_order(order_id, reader_id))


# ─────────────────────────────────────────────
# WORKFLOW TESTING
# ─────────────────────────────────────────────
section("WORKFLOW TESTING")

if order_id and user_id:
    print(f"\n[product_order_mount({order_id})]")
    ok(*db.product_order_mount(order_id, user_id))
    print("  Double mount attempt:")
    ok(*db.product_order_mount(order_id, user_id))

    print(f"\n[product_order_test({order_id})]")
    ok(*db.product_order_test(order_id, user_id))
    print("  Double test attempt:")
    ok(*db.product_order_test(order_id, user_id))

    print(f"\n[product_order_ship({order_id})]")
    ok(*db.product_order_ship(order_id, user_id))
    print("  Double ship attempt:")
    ok(*db.product_order_ship(order_id, user_id))

    print(f"\n[product_order_activate({order_id})]")
    ok(*db.product_order_activate(order_id, user_id))
    print("  Double activate attempt:")
    ok(*db.product_order_activate(order_id, user_id))

    print(f"\n[get_product_order({order_id}) after complete lifecycle]")
    p("final_order", db.get_product_order(order_id))


# ─────────────────────────────────────────────
# ERROR TESTING
# ─────────────────────────────────────────────
section("ERROR TESTING")

print("\n[add_product_order with invalid created_by=99999]")
ok(
    *db.add_product_order(
        order_number=99999,
        client_name="Test Client",
        client_cnpj=None,
        product_code="TEST",
        product_description=None,
        product_family=None,
        reader_id=None,
        created_by=99999,
    )
)

if reader_id and user_id:
    print(f"\n[add_product_order with unavailable reader {reader_id}]")
    ok(
        *db.add_product_order(
            order_number=88888,
            client_name="Test Client",
            client_cnpj=None,
            product_code="TEST",
            product_description=None,
            product_family=None,
            reader_id=reader_id,
            created_by=user_id,
        )
    )


# ─────────────────────────────────────────────
# FINAL DATA DISPLAY
# ─────────────────────────────────────────────
section("FINAL DATA DISPLAY")

print("\n[get_product_orders - final state]")
p("final_orders", db.get_product_orders())


# ─────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────
section("CLEANUP")
do_cleanup = input("\n  Delete all created test data? (y/N): ").strip().lower() == "y"

if do_cleanup:
    if order_id:
        print(f"\n[delete_product_order({order_id})]")
        ok(*db.delete_product_order(order_id))
        if reader_id:
            print(f"  Reader {reader_id} should be available again:")
            p("reader", db.get_reader(reader_id))

    if reader_id:
        print(f"\n[delete_reader({reader_id})]")
        ok(*db.delete_reader(reader_id))

    if rt_id:
        print(f"\n[delete_reader_type({rt_id})]")
        ok(*db.delete_reader_type(rt_id))

    if user_id:
        print(f"\n[delete_user({user_id})]")
        ok(*db.delete_user(user_id))

    print("\n  Cleanup done.")
else:
    print("  Skipped.")

section("DONE")
