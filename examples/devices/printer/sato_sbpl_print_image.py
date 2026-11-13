"""Print a complete SBPL label (text, barcodes, 2D codes and shapes) on a SATO printer.

SBPL features not available in ZPL printers (e.g. scalable fonts, Aztec, form overlays) are
available through the ``SbplLabel`` builder.
"""

import asyncio
import logging
from pathlib import Path

from PIL import Image, ImageOps

from smartx_rfid.devices import SatoSbplPrinter
from smartx_rfid.devices.printer import SbplLabel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

printer = SatoSbplPrinter(ip="192.168.0.112", port=9100, read_before_print=True)
EPC_TO_WRITE = "112233445566"

IMAGE_PATH = Path(__file__).with_name("Shopee-preto_SBPL.png")
# 50 x 12 mm at 305 dpi (approximately 12 dots/mm).
LABEL_WIDTH = 600
LABEL_HEIGHT = 144
IMAGE_MARGIN = 12

SCALE_FACTOR: float = 0.9  # Aceita valores intermediários, como 1.1, 1.25 ou 1.5.


def image_as_monochrome_bitmap() -> tuple[bytes, tuple[int, int]]:
    """Convert the transparent PNG to the packed monochrome bitmap used by SBPL <G>."""
    with Image.open(IMAGE_PATH) as source:
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        image = ImageOps.contain(
            background.convert("L"),
            (LABEL_WIDTH - IMAGE_MARGIN * 2, LABEL_HEIGHT - IMAGE_MARGIN * 2),
            method=Image.Resampling.LANCZOS,
        )
        # Widen the logo by about 10%; keep its height within the V0100 printable area.
        scaled_size = (
            max(1, round(image.width * SCALE_FACTOR)),
            max(1, round(image.height * SCALE_FACTOR)),
        )
        image = image.resize(scaled_size, Image.Resampling.LANCZOS)
        # Reverse black and white: print the dark logo white on a black background.
        image = image.point(lambda value: 255 if value < 170 else 0).convert("1")
        # The working printer command encodes graphic height in 8-row units.
        padded_height = (image.height + 7) // 8 * 8
        if padded_height != image.height:
            image = ImageOps.expand(image, border=(0, 0, 0, padded_height - image.height), fill=0)

    return image.tobytes(), image.size


def build_label() -> SbplLabel:
    bitmap, (image_width, image_height) = image_as_monochrome_bitmap()
    width_bytes = (image_width + 7) // 8
    graphic_header = f"\x1bGH{width_bytes:03d}{image_height // 8:03d}".encode("ascii")
    graphic_data = graphic_header + bitmap.hex().upper().encode("ascii")
    return (
        SbplLabel()
        .write_rfid(epc=EPC_TO_WRITE)
        # Match the known-good command order and use the printer's configured media size.
        # V0100 is the known-good vertical origin; smaller artwork keeps it inside the label.
        .raw(b"\x1bH0060\x1bV0090")
        .raw(graphic_data)
        .qr_code(EPC_TO_WRITE, x=480, y=100)
        .text(EPC_TO_WRITE, x=460, y=190, font="XS")
        .quantity(1)
    )


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> {event_type}: {event_data}")
    if event_type == "status" and event_data == "ready" and not getattr(on_event, "sent", False):
        label = build_label()
        sbpl_code = label.build().replace(b"\x1b", b"<ESC>").decode("ascii", errors="replace")
        print(f"SBPL gerado:\n{sbpl_code}")
        ok, result = printer.print(label)
        on_event.sent = ok
        print(f"Print sent, ID: {result}" if ok else f"Print error: {result}")
    if event_type in ("print_success", "print_error"):
        raise SystemExit(0)


async def main():
    printer.on_event = on_event
    asyncio.create_task(printer.connect())
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
