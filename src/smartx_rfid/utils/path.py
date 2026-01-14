import importlib
import logging
import sys
from pathlib import Path


def get_frozen_path(relative_path: str) -> Path:
    """
    Return the absolute path to a file or directory, taking into account
    whether the application is running from source or as a frozen executable.

    Args:
        relative_path: Relative path to the file or directory.

    Returns:
        The resolved absolute path.
    """
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(sys.argv[0]).resolve().parent

    return base_path / relative_path


def get_prefix_from_path(current_file: str, base_dir: str = "routers") -> str:
    """
    Automatically generate an API router prefix based on the folder structure
    starting from the given base directory.

    Args:
        current_file: Usually __file__.
        base_dir: Root directory name for routers.

    Returns:
        The router prefix (e.g. "/rfid/get").
    """
    path = Path(current_file).resolve()
    parts = path.parts

    if base_dir not in parts:
        raise ValueError(f"'{base_dir}' not found in path: {path}")

    base_index = parts.index(base_dir)
    prefix_parts = parts[base_index + 1 :]
    prefix_string = "/" + "/".join(prefix_parts)

    return prefix_string.replace(".py", "")


def include_all_routers(current_path: str, app) -> None:
    """
    Recursively discover and include all API routers found in the given path.
    """
    routes_path = get_frozen_path(current_path)

    for entry in Path(routes_path).iterdir():
        if entry.is_dir() and entry.name != "__pycache__":
            include_all_routers(str(Path(current_path) / entry.name), app)

        elif entry.is_file() and entry.suffix == ".py" and entry.name != "__init__.py":
            module_name = entry.stem
            file_path = entry

            spec = importlib.util.spec_from_file_location(f"app.routers.{module_name}", str(file_path))
            module = importlib.util.module_from_spec(spec)

            try:
                spec.loader.exec_module(module)

                if hasattr(module, "router"):
                    prefix = getattr(module.router, "prefix", "") or ""
                    app.include_router(
                        module.router,
                        include_in_schema=prefix.startswith("/api"),
                    )

                    try:
                        routers_dir = Path(routes_path).resolve()
                        relative_path = file_path.resolve().relative_to(routers_dir.parent)
                    except Exception:
                        relative_path = file_path.name

                    logging.info(f"✅ Route loaded: {relative_path}")

                else:
                    logging.warning(f"⚠️  File {current_path} does not define a 'router'")

            except Exception as e:
                logging.error(f"❌ Error loading {current_path}: {e}", exc_info=True)


def load_swagger_description(swagger_file_path: str) -> str:
    """
    Load the Swagger markdown description from a file.

    Returns:
        The markdown content as a string, or a default message if loading fails.
    """
    try:
        with open(swagger_file_path, "r", encoding="utf-8") as file:
            return file.read()

    except FileNotFoundError:
        logging.warning(f"{swagger_file_path} not found. Using default description.")
        return "API documentation not found."

    except Exception as e:
        logging.error(f"Error loading Swagger documentation: {e}")
        return "Error loading API documentation."
