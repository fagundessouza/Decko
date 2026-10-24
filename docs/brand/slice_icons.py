"""Cut the Decko icon sheet into one PNG per icon.

    uv run --with pillow python docs/brand/fatiar-icones.py \
        docs/brand/icones-folha-original.png apps/web/src/assets/icons

The sheet is a 7x5 grid, but not an exact one: cutting on fixed cell borders takes a
slice of the neighbour and clips whatever reaches past the cell — the leaf under the
drone, for one. So each icon is found by its own alpha channel (the sheet ships with the
background removed) and the grid is used only to decide which pieces belong together.
"""

import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

SHEET = Path(sys.argv[1])
TARGET = Path(sys.argv[2])
COLUMNS, ROWS = 7, 5
# 128 covers a 64px slot on a 2x screen, and the largest slot in the app is 48px.
# Lightness is a requirement here: 192 made the seven icons in the bundle weigh 267 KB.
SIDE = 128
MARGIN = 0.05  # breathing room inside the square, as a fraction of the side

# Scale the search runs at. Smaller is faster and joins the loose parts of one icon
# (the drone's water drops, the scanner's cable) more readily.
SHRINK = 4
# How much each piece swells before looking for neighbours. Small on purpose: joining the
# parts of one icon is the grid's job below, and swelling enough to do it here would
# touch the icon above.
GLUE = 3

NAMES = [
    "home",
    "terminal",
    "boxes",
    "apps",
    "settings",
    "drone",
    "store",
    "dashboard",
    "cart",
    "price-tag",
    "chart",
    "people",
    "calendar",
    "checklist",
    "coin",
    "card",
    "register",
    "wallet",
    "bank",
    "safe",
    "document",
    "truck",
    "pallet",
    "scanner",
    "discount",
    "megaphone",
    "mail",
    "chat",
    "shield",
    "cloud",
    "folder",
    "database",
    "download",
    "printer",
    "mobile",
]


def pieces(sheet: Image.Image) -> list[tuple[int, int, int, int]]:
    """Every connected blob of ink, in sheet coordinates."""
    alpha = sheet.getchannel("A").reduce(SHRINK).point(lambda v: 255 if v > 24 else 0)
    alpha = alpha.filter(ImageFilter.MaxFilter(GLUE))

    width, height = alpha.size
    pixels = alpha.load()
    seen = bytearray(width * height)
    boxes: list[tuple[int, int, int, int]] = []

    for start_y in range(height):
        for start_x in range(width):
            if seen[start_y * width + start_x] or not pixels[start_x, start_y]:
                continue

            queue = deque([(start_x, start_y)])
            seen[start_y * width + start_x] = 1
            x0 = x1 = start_x
            y0 = y1 = start_y
            area = 0

            while queue:
                x, y = queue.popleft()
                area += 1
                x0, x1 = min(x0, x), max(x1, x)
                y0, y1 = min(y0, y), max(y1, y)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    index = ny * width + nx
                    if seen[index] or not pixels[nx, ny]:
                        continue
                    seen[index] = 1
                    queue.append((nx, ny))

            # Stray speckles are not icons.
            if area < 200:
                continue
            # Undo the glue and go back to the sheet's own scale.
            back = GLUE // 2
            boxes.append(
                (
                    max(0, (x0 + back) * SHRINK),
                    max(0, (y0 + back) * SHRINK),
                    min(sheet.width, (x1 - back + 1) * SHRINK),
                    min(sheet.height, (y1 - back + 1) * SHRINK),
                )
            )

    return boxes


def by_cell(
    sheet: Image.Image, boxes: list[tuple[int, int, int, int]]
) -> list[tuple[int, int, int, int]]:
    """Group the pieces by the grid cell their centre falls in.

    The grid only groups: the crop stays the union of the pieces found, so nothing is
    clipped for reaching outside its cell.
    """
    width = sheet.width / COLUMNS
    height = sheet.height / ROWS
    cells: dict[tuple[int, int], tuple[int, int, int, int]] = {}

    for x0, y0, x1, y1 in boxes:
        column = min(COLUMNS - 1, int(((x0 + x1) / 2) // width))
        row = min(ROWS - 1, int(((y0 + y1) / 2) // height))
        current = cells.get((row, column))
        cells[(row, column)] = (
            (x0, y0, x1, y1)
            if current is None
            else (
                min(current[0], x0),
                min(current[1], y0),
                max(current[2], x1),
                max(current[3], y1),
            )
        )

    return [cells[key] for key in sorted(cells)]


def squared(sheet: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    icon = sheet.crop(box)
    # Trim again, now without the glue, so the icon really sits in the middle.
    tight = icon.getbbox()
    if tight is not None:
        icon = icon.crop(tight)

    usable = round(SIDE * (1 - 2 * MARGIN))
    icon.thumbnail((usable, usable), Image.LANCZOS)

    canvas = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
    canvas.paste(icon, ((SIDE - icon.width) // 2, (SIDE - icon.height) // 2))
    return canvas


def main() -> None:
    sheet = Image.open(SHEET).convert("RGBA")
    boxes = by_cell(sheet, pieces(sheet))
    print(f"found {len(boxes)} icons, expected {COLUMNS * ROWS}")
    if len(boxes) != len(NAMES):
        raise SystemExit("count differs from the grid; adjust GLUE or the minimum area")

    TARGET.mkdir(parents=True, exist_ok=True)
    for name, box in zip(NAMES, boxes, strict=True):
        path = TARGET / f"{name}.png"
        squared(sheet, box).save(path, optimize=True)
        print(f"{path.name}: {path.stat().st_size // 1024} KB")


main()
