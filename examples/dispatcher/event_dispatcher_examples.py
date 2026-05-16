from smartx_rfid.dispatcher import EventDispatcher


def main():
    dispatcher = EventDispatcher(
        dispatches_path="examples/dispatcher/dispatches",
        example_path="examples/dispatcher/dispatches_examples",
    )

    names = dispatcher.get_example_names()

    if not names:
        print("No examples found.")
        return

    print("Available examples:")
    for i, name in enumerate(names, start=1):
        print(f"  [{i}] {name}")

    try:
        choice = int(input("\nSelect an example by number: "))
        if not 1 <= choice <= len(names):
            print("Invalid selection.")
            return
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    example_name = names[choice - 1]
    content = dispatcher.get_example_content(example_name)

    if content:
        print(f"\nContent of {example_name}:")
        print(content)
    else:
        print(f"\nFailed to load content of {example_name}.")


if __name__ == "__main__":
    print("Tip: run examples/dispatcher/dispatch_crud_example.py for full CRUD + queue usage.")
    main()
