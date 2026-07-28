#!/usr/bin/env python3
"""Interactive example for ApiXtrack.

Prompts the user for an action level (GET / REGISTER / DELETE / MOVE / OTHER)
and then for a specific action. Collects required parameters and calls the
corresponding `ApiXtrack` coroutine.

Run from repository root:
    python3 examples/api/xtrack/xtrack.py
"""

import sys
import asyncio
import logging
from pprint import pprint

sys.path.insert(0, "src")

from smartx_rfid.api.xtrack import ApiXtrack, demo_server_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def input_with_default(prompt: str, default: str = "") -> str:
    raw = input(f"{prompt}" + (f" [{default}]" if default != "" else "") + ": ").strip()
    return raw if raw != "" else default


def parse_bool(val: str, default: bool = False) -> bool:
    if val == "":
        return default
    v = val.strip().lower()
    return v in ("1", "y", "yes", "true", "t")


def parse_int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return default


def pretty_print_result(result):
    success, data = result
    print("\n--- RESULT ---")
    print("Success:", success)
    if isinstance(data, list):
        print(f"Returned {len(data)} items")
        pprint(data[:20])
        if len(data) > 20:
            print("(...truncated)")
    else:
        pprint(data)
    print("--- END ---\n")


ACTION_MAP = {
    "GET": [
        ("get_categories", "List categories", []),
        ("get_conditions", "List conditions", []),
        ("get_cost_centers", "List cost centers", []),
        ("get_custodians", "List custodians", []),
        ("get_departments", "List departments", []),
        ("get_disposals", "List disposals", []),
        ("get_dispositions", "List dispositions", []),
        ("get_groups", "List groups", []),
        ("get_locations", "List locations", []),
        ("get_products", "List products", []),
        ("get_objects", "List objects", []),
        ("get_identifications", "List identifications", []),
        ("get_users", "List users", []),
        ("get_idcode_from_epc", "Get IDCODE by EPC", [("epc", str, "")]),
        ("get_object_by_epc", "Get object by EPC", [("epc", str, "")]),
        ("get_object_by_idcode", "Get object by IDCODE", [("idcode", str, "")]),
    ],
    "REGISTER": [
        ("register_category", "Create category", [("category_name", str, "")]),
        ("register_condition", "Create condition", [("condition_name", str, "")]),
        ("register_cost_center", "Create cost center", [("cost_center_name", str, "")]),
        ("register_custodian", "Create custodian", [("custodian_name", str, ""), ("custodian_description", str, "")]),
        ("register_department", "Create department", [("department_name", str, "")]),
        ("register_disposal", "Create disposal", [("disposal_name", str, "")]),
        ("register_disposition", "Create disposition", [("disposition_name", str, ""), ("epc", str, "")]),
        ("register_group", "Create group", [("group_name", str, "")]),
        (
            "register_location",
            "Create location",
            [
                ("location_name", str, ""),
                ("allocable", bool, True),
                ("idetype1", str, ""),
                ("idecode1", str, ""),
                ("idetype2", str, ""),
                ("idecode2", str, ""),
                ("idetype3", str, ""),
                ("idecode3", str, ""),
                ("idetype4", str, ""),
                ("idecode4", str, ""),
            ],
        ),
        (
            "register_product",
            "Create product (item model)",
            [
                ("idcode", str, ""),
                ("description", str, ""),
                ("category", str, ""),
                ("gs1ref", str, ""),
                ("container", int, 0),
            ]
            + [(f"usrdata{i}", str, "") for i in range(1, 10)]
            + [(f"idetype{i}", str, "") for i in range(1, 5)]
            + [(f"idecode{i}", str, "") for i in range(1, 5)]
            + [("imagefile", str, "")],
        ),
        (
            "register_object",
            "Create object",
            [
                ("active", int, 1),
                ("idcode", str, ""),
                ("description", str, ""),
                ("serialnumber", str, ""),
                ("quantity", int, 1),
                ("itemmodel_idcode", str, ""),
                ("department_name", str, ""),
                ("condition_name", str, ""),
                ("disposition_name", str, ""),
                ("location_name", str, ""),
            ]
            + [("homelocation_name", str, "")]
            + [
                ("group_name", str, ""),
                ("custodian_name", str, ""),
                ("disposal_name", str, ""),
                ("costcenter_name", str, ""),
                ("container_idcode", str, ""),
                ("latitude", str, ""),
                ("longitude", str, ""),
            ]
            + [(f"usrdata{i}", str, "") for i in range(1, 10)]
            + [
                ("idetype1", str, "BARCODE"),
                ("idecode1", str, ""),
                ("idetype2", str, "RFID"),
                ("idecode2", str, ""),
                ("idetype3", str, ""),
                ("idecode3", str, ""),
                ("idetype4", str, ""),
                ("idecode4", str, ""),
                ("imagefile", str, ""),
            ],
        ),
    ],
    "DELETE": [
        ("delete_category", "Delete category", [("category_name", str, "")]),
        ("delete_all_categories", "Delete all categories", []),
        ("delete_condition", "Delete condition", [("condition_name", str, "")]),
        ("delete_all_conditions", "Delete all conditions", []),
        ("delete_cost_center", "Delete cost center", [("cost_center_name", str, "")]),
        ("delete_all_cost_centers", "Delete all cost centers", []),
        ("delete_custodian", "Delete custodian", [("custodian_name", str, "")]),
        ("delete_all_custodians", "Delete all custodians", []),
        ("delete_department", "Delete department", [("department_name", str, "")]),
        ("delete_all_departments", "Delete all departments", []),
        ("delete_disposal", "Delete disposal", [("disposal_name", str, "")]),
        ("delete_all_disposals", "Delete all disposals", []),
        ("delete_disposition", "Delete disposition", [("disposition_name", str, ""), ("epc_uri", str, "")]),
        ("delete_all_dispositions", "Delete all dispositions", []),
        ("delete_group", "Delete group", [("group_name", str, "")]),
        ("delete_all_groups", "Delete all groups", []),
        ("delete_location", "Delete location", [("location_name", str, "")]),
        ("delete_all_locations", "Delete all locations", []),
        ("delete_item_model", "Delete item model", [("idcode", str, "")]),
        ("delete_all_item_models", "Delete all item models", []),
        ("delete_object", "Delete object", [("idcode", str, "")]),
        ("delete_all_objects", "Delete all objects", []),
    ],
    "MOVE": [
        ("move_object", "Move object to location", [("idcode", str, ""), ("location_id", str, "")]),
        ("move_condition", "Move object condition", [("idcode", str, ""), ("condition", str, "")]),
        ("move_disposition", "Move object disposition", [("idcode", str, ""), ("disposition", str, "")]),
        ("move_custodian", "Move object custodian", [("idcode", str, ""), ("custodian", str, "")]),
        ("move_cost_center", "Move object cost center", [("idcode", str, ""), ("costcenter", str, "")]),
        ("move_group", "Move object group", [("idcode", str, ""), ("group", str, "")]),
        ("move_disposal", "Move object disposal", [("idcode", str, ""), ("disposal", str, "")]),
        ("move_department", "Move object department", [("idcode", str, ""), ("department", str, "")]),
    ],
    "UPDATE": [
        (
            "update_usrdata",
            "Update user data fields",
            [("idcode", str, "")] + [(f"usrdata{i}", str, "") for i in range(1, 10)],
        ),
        ("update_home_location", "Update home location", [("idcode", str, ""), ("homelocation", str, "")]),
        ("update_active", "Update active flag", [("idcode", str, ""), ("active", str, "true")]),
        ("update_due_date", "Update due date", [("idcode", str, ""), ("duedate", str, "")]),
        ("update_last_seen", "Update last seen", [("idcode", str, ""), ("lastseen", str, "")]),
    ],
    "OTHER": [
        ("test_connection", "Test API connection", []),
        (
            "get_rep_hist_loc",
            "Get report history location",
            [("startdate", str, ""), ("enddate", str, ""), ("object_id", str, ""), ("column", str, "LOCATION")],
        ),
    ],
}


async def run_action(api: ApiXtrack, method_name: str, params: list):
    method = getattr(api, method_name, None)
    if method is None:
        print(f"Method {method_name} not found on ApiXtrack")
        return
    # call coroutine with positional args
    try:
        result = await method(*params)
        pretty_print_result(result)
    except Exception as e:
        print("Call failed:", e)


async def interactive_loop():
    base = input_with_default("Base URL", demo_server_url)
    api = ApiXtrack(base)

    while True:
        print("\n===== ApiXtrack Interactive Menu =====")
        print("Levels:")
        for i, lvl in enumerate(ACTION_MAP.keys(), 1):
            print(f"  {i}. {lvl}")
        print("  0. Exit")
        lvl_choice = input_with_default("Choose level (name or number)")
        if lvl_choice == "0" or lvl_choice.lower() in ("exit", "q", "quit"):
            break

        # allow numeric or name
        lvl_keys = list(ACTION_MAP.keys())
        if lvl_choice.isdigit():
            idx = int(lvl_choice) - 1
            if idx < 0 or idx >= len(lvl_keys):
                print("Invalid level")
                continue
            level = lvl_keys[idx]
        else:
            level = lvl_choice.upper()
            if level not in ACTION_MAP:
                print("Unknown level")
                continue

        actions = ACTION_MAP[level]
        print(f"\nActions for {level}:")
        for i, (mname, descr, params) in enumerate(actions, 1):
            print(f"  {i}. {mname} - {descr}")
        print("  0. Back")
        act_choice = input_with_default("Choose action (number)")
        if act_choice == "0":
            continue
        if not act_choice.isdigit() or int(act_choice) - 1 not in range(len(actions)):
            print("Invalid action")
            continue
        act_idx = int(act_choice) - 1
        method_name, descr, params_spec = actions[act_idx]

        # collect params
        collected = []
        for name, ptype, default in params_spec:
            if ptype is bool:
                raw = input_with_default(f"{name} (y/n)", "y" if default else "n")
                val = parse_bool(raw, default)
            elif ptype is int:
                raw = input_with_default(f"{name}", str(default))
                val = parse_int(raw, default)
            else:
                raw = input_with_default(f"{name}", default)
                val = raw
            collected.append(val)

        await run_action(api, method_name, collected)

        cont = input_with_default("Do another action? (Y/n)", "Y")
        if cont.lower() in ("n", "no", "0"):
            break


def main():
    asyncio.run(interactive_loop())


if __name__ == "__main__":
    main()
