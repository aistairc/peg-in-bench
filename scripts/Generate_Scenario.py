#!/usr/bin/env python3
import argparse
import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageGrab, ImageTk
except ImportError:
    Image = None
    ImageGrab = None
    ImageTk = None

SHAPES = ["triangle", "rectangle", "circle", "hexagon", "L-shape"]
TOLERANCES = ["0.2 mm", "1 mm", "3 mm"]
ORIENTATIONS = ["0°", "45°", "90°", "135°", "180°", "225°", "270°", "315°"]
BASE_ORIENTATIONS = ["0°", "90°", "180°", "270°"]
DEFAULT_IMAGE_DIR = "Photos"
DEFAULT_DIAGONAL_IMAGE_DIR = "Photos_45"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

GRID_POSITIONS = [
    ("top-left", (0, 0)),
    ("top-center", (0, 1)),
    ("top-right", (0, 2)),
    ("middle-left", (1, 0)),
    ("middle-right", (1, 2)),
    ("bottom-left", (2, 0)),
    ("bottom-center", (2, 1)),
    ("bottom-right", (2, 2)),
]

TASK5_PATTERNS = {
    "corner_plus_center": [(0, 0), (0, 2), (1, 1), (2, 0), (2, 2)],
    "sides_only": [(0, 1), (1, 0), (1, 2), (2, 1)],
}

BASE_CONNECTION_PORTS = {
    "base": 4,
    "corner-base": 2,
    "line-base": 2,
    "cross-base": 1,
}

BASE_CAN_ACCEPT = {
    "base": True,
    "corner-base": True,
    "line-base": True,
    "cross-base": False,
}

SIDES = ["north", "east", "south", "west"]
SIDE_INDEX = {side: idx for idx, side in enumerate(SIDES)}
OPPOSITE_SIDE = {
    "north": "south",
    "east": "west",
    "south": "north",
    "west": "east",
}

# Rule: one side must provide a joint and the opposite side must provide a hole.
PIECE_CONNECTORS_0 = {
    "base": {"north": "hole", "east": "hole", "south": "hole", "west": "hole"},
    "line-base": {"north": "hole", "east": "joint", "south": "hole", "west": "joint"},
    "corner-base": {"north": "joint", "east": "joint", "south": "hole", "west": "hole"},
    "cross-base": {"north": "joint", "east": "joint", "south": "joint", "west": "joint"},
}


def _parse_orientation_degrees(value: str) -> int:
    text = value.strip().replace("°", "")
    try:
        return int(round(float(text))) % 360
    except ValueError:
        return 0

def random_orientation() -> str:
    return random.choice(ORIENTATIONS)


def random_base_orientation() -> str:
    return random.choice(BASE_ORIENTATIONS)


def _rotate_side(side: str, orientation: str) -> str:
    steps = (_parse_orientation_degrees(orientation) // 90) % 4
    idx = SIDE_INDEX[side]
    return SIDES[(idx + steps) % 4]

def connector_for_side(piece_type: str, orientation: str, world_side: str) -> str:
    mapping = PIECE_CONNECTORS_0.get(piece_type, PIECE_CONNECTORS_0["base"])
    # Convert world-side query into the piece-local side at 0°.
    steps = (_parse_orientation_degrees(orientation) // 90) % 4
    local_idx = (SIDE_INDEX[world_side] - steps) % 4
    local_side = SIDES[local_idx]
    return mapping.get(local_side, "none")

def connectors_compatible(connector_a: str, connector_b: str) -> bool:
    return (connector_a == "joint" and connector_b == "hole") or (connector_a == "hole" and connector_b == "joint")

def find_valid_layout_orientations(
    layout_types: Dict[str, str],
    required_edges: List[Tuple[str, str, str, str]],
    allowed_orientations_by_slot: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, str]:
    slots = list(layout_types.keys())
    all_orientations = ["0°", "90°", "180°", "270°"]

    def backtrack(idx: int, chosen: Dict[str, str]) -> Optional[Dict[str, str]]:
        if idx == len(slots):
            return chosen.copy()

        slot = slots[idx]
        piece_type = layout_types[slot]
        allowed = all_orientations
        if allowed_orientations_by_slot and slot in allowed_orientations_by_slot:
            allowed = allowed_orientations_by_slot[slot]
        for orientation in allowed:
            chosen[slot] = orientation
            valid = True
            for left_slot, left_side, right_slot, right_side in required_edges:
                if left_slot not in chosen or right_slot not in chosen:
                    continue
                c1 = connector_for_side(layout_types[left_slot], chosen[left_slot], left_side)
                c2 = connector_for_side(layout_types[right_slot], chosen[right_slot], right_side)
                if not connectors_compatible(c1, c2):
                    valid = False
                    break
            if valid:
                result = backtrack(idx + 1, chosen)
                if result is not None:
                    return result
            chosen.pop(slot, None)
        return None

    result = backtrack(0, {})
    if result is None:
        raise RuntimeError("No valid orientation assignment found for required base connections.")
    return result


def build_layout_connection_plan(
    row_name: str,
    layout_types: Dict[str, str],
    layout_orientations: Dict[str, str],
    required_edges: List[Tuple[str, str, str, str]],
) -> Dict[str, Any]:
    inventory_start = {base: 3 for base in BASE_CONNECTION_PORTS}
    inventory_remaining = inventory_start.copy()
    for piece_type in layout_types.values():
        inventory_remaining[piece_type] = inventory_remaining.get(piece_type, 0) - 1

    slot_to_piece_id = {slot: f"P{idx + 1}" for idx, slot in enumerate(layout_types.keys())}
    joints: List[Dict[str, Any]] = []
    steps: List[str] = []

    anchor_slot = next(iter(layout_types.keys()))
    steps.append(
        f"Place {slot_to_piece_id[anchor_slot]} ({layout_types[anchor_slot]}, {layout_orientations[anchor_slot]}) as row anchor."
    )

    for left_slot, left_side, right_slot, right_side in required_edges:
        left_type = layout_types[left_slot]
        right_type = layout_types[right_slot]
        left_orientation = layout_orientations[left_slot]
        right_orientation = layout_orientations[right_slot]
        c1 = connector_for_side(left_type, left_orientation, left_side)
        c2 = connector_for_side(right_type, right_orientation, right_side)

        if not connectors_compatible(c1, c2):
            raise RuntimeError(
                f"Invalid edge {left_slot}->{right_slot}: {left_type}({left_side},{c1}) vs {right_type}({right_side},{c2})"
            )

        joints.append(
            {
                "from": slot_to_piece_id[left_slot],
                "to": slot_to_piece_id[right_slot],
                "from_side": left_side,
                "to_side": right_side,
                "connectors": f"{c1}->{c2}",
            }
        )
        steps.append(
            f"Connect {slot_to_piece_id[right_slot]} ({right_type}, {right_orientation}) {right_side} to "
            f"{slot_to_piece_id[left_slot]} ({left_type}, {left_orientation}) {left_side} using {c1}->{c2}."
        )

    return {
        "row_name": row_name,
        "piece_order": [layout_types[slot] for slot in layout_types],
        "piece_orientations": [layout_orientations[slot] for slot in layout_types],
        "slot_order": list(layout_types.keys()),
        "inventory_start": inventory_start,
        "inventory_remaining": inventory_remaining,
        "joints": joints,
        "steps": steps,
    }

def _normalize_shape_token(value: str) -> str:
    token = "".join(ch for ch in value.lower() if ch.isalnum())
    aliases = {
        "emptybase": "base",
        "cornerbase1": "cornerbase",
        "cornerbase2": "cornerbase",
        "cornerbase3": "cornerbase",
    }
    return aliases.get(token, token)

def _normalize_tolerance_token(value: str) -> str:
    lowered = value.lower().replace("mm", "")
    filtered = "".join(ch for ch in lowered if ch.isdigit() or ch == ".")
    return filtered or lowered.strip()

def _parse_image_filename(stem: str) -> Optional[Tuple[str, str]]:
    if "_" not in stem:
        return None
    shape_part, tolerance_part = stem.rsplit("_", 1)
    shape_key = _normalize_shape_token(shape_part)
    tolerance_key = _normalize_tolerance_token(tolerance_part)
    if not shape_key or not tolerance_key:
        return None
    return shape_key, tolerance_key

def _strip_angle_suffix(stem: str, suffix: str = "45") -> str:
    marker = f"_{suffix}"
    if stem.lower().endswith(marker.lower()):
        return stem[: -len(marker)]
    return stem

def _directory_has_images(path: Path) -> bool:
    if not path.is_dir():
        return False
    for child in path.iterdir():
        if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
            return True
    return False

def _resolve_image_root(path: Optional[Path]) -> Optional[Path]:
    if path is None:
        return None
    if not path.exists() or not path.is_dir():
        return path
    if _directory_has_images(path):
        return path
    for child in sorted(path.iterdir()):
        if _directory_has_images(child):
            return child
    return path

def _resolve_diagonal_image_root(original_path: Optional[Path], resolved_path: Optional[Path]) -> Optional[Path]:
    candidates: List[Path] = []

    for base in (original_path, resolved_path):
        if base is None:
            continue
        candidates.append(base.parent / f"{base.name}_45")
        if base.parent != base:
            candidates.append(base.parent.parent / f"{base.parent.name}_45")

    candidates.append(Path(DEFAULT_DIAGONAL_IMAGE_DIR))

    seen: set[Path] = set()
    for candidate in candidates:
        expanded = candidate.expanduser()
        if expanded in seen:
            continue
        seen.add(expanded)
        if expanded.exists() and expanded.is_dir():
            return _resolve_image_root(expanded)
    return None

def _remove_uniform_background(image: Any, channel_tolerance: int = 30) -> Any:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size

    sample_points = [
        (0, 0),
        (max(0, width - 1), 0),
        (0, max(0, height - 1)),
        (max(0, width - 1), max(0, height - 1)),
    ]
    samples = [pixels[x, y] for x, y in sample_points]
    r_vals = [p[0] for p in samples]
    g_vals = [p[1] for p in samples]
    b_vals = [p[2] for p in samples]

    if (max(r_vals) - min(r_vals) > channel_tolerance or
            max(g_vals) - min(g_vals) > channel_tolerance or
            max(b_vals) - min(b_vals) > channel_tolerance):
        return rgba

    bg_r = sum(r_vals) // len(r_vals)
    bg_g = sum(g_vals) // len(g_vals)
    bg_b = sum(b_vals) // len(b_vals)

    # Use a stricter filter for black backgrounds so dark piece details are preserved.
    bg_brightness = max(bg_r, bg_g, bg_b)
    if bg_brightness <= 40:
        match_tolerance = min(14, channel_tolerance)
        dark_cutoff = 32
    else:
        # Use a relaxed threshold for JPG compression artifacts on lighter backgrounds.
        match_tolerance = max(24, channel_tolerance + 10)
        dark_cutoff = 255

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if (
                a > 0 and
                max(r, g, b) <= dark_cutoff and
                abs(r - bg_r) <= match_tolerance and
                abs(g - bg_g) <= match_tolerance and
                abs(b - bg_b) <= match_tolerance
            ):
                pixels[x, y] = (r, g, b, 0)
    return rgba

class PieceImageStore:
    def __init__(self, image_dir: Optional[str] = None) -> None:
        self.image_dir: Optional[Path] = None
        self.diagonal_image_dir: Optional[Path] = None
        self._base_cache: Dict[Tuple[str, str, str], Any] = {}
        self._photo_cache: Dict[Tuple[str, str, int, int], Any] = {}
        self._path_index: Dict[Tuple[str, str], Path] = {}
        self._shape_only_index: Dict[str, Path] = {}
        self._diagonal_path_index: Dict[Tuple[str, str], Path] = {}
        self._diagonal_shape_only_index: Dict[str, Path] = {}
        self._path_index_built = False
        self._diagonal_path_index_built = False
        self.set_image_dir(image_dir)

    def set_image_dir(self, image_dir: Optional[str]) -> None:
        original_path = Path(image_dir).expanduser() if image_dir else None
        path = _resolve_image_root(original_path)
        diagonal_path = _resolve_diagonal_image_root(original_path, path)
        if path == self.image_dir and diagonal_path == self.diagonal_image_dir:
            return
        self.image_dir = path
        self.diagonal_image_dir = diagonal_path
        self._base_cache.clear()
        self._photo_cache.clear()
        self._path_index.clear()
        self._shape_only_index.clear()
        self._diagonal_path_index.clear()
        self._diagonal_shape_only_index.clear()
        self._path_index_built = False
        self._diagonal_path_index_built = False

    def _build_path_index(self, use_diagonal: bool = False) -> None:
        root = self.diagonal_image_dir if use_diagonal else self.image_dir
        if use_diagonal:
            self._diagonal_path_index = {}
            self._diagonal_shape_only_index = {}
            self._diagonal_path_index_built = True
        else:
            self._path_index = {}
            self._shape_only_index = {}
            self._path_index_built = True

        if root is None or not root.is_dir():
            return

        for child in root.iterdir():
            if not child.is_file() or child.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            stem = _strip_angle_suffix(child.stem) if use_diagonal else child.stem
            shape_only_key = _normalize_shape_token(stem)
            shape_index = self._diagonal_shape_only_index if use_diagonal else self._shape_only_index
            path_index = self._diagonal_path_index if use_diagonal else self._path_index
            if shape_only_key and shape_only_key not in shape_index:
                shape_index[shape_only_key] = child
            parsed = _parse_image_filename(stem)
            if parsed is not None:
                path_index[parsed] = child

    def _load_base_image_from_index(self, shape: str, tolerance: str, use_diagonal: bool = False) -> Any:
        root = self.diagonal_image_dir if use_diagonal else self.image_dir
        if Image is None or root is None:
            return None

        variant = "diagonal" if use_diagonal else "default"
        key = (shape, tolerance, variant)
        if key in self._base_cache:
            return self._base_cache[key]

        if use_diagonal:
            if not self._diagonal_path_index_built:
                self._build_path_index(use_diagonal=True)
            path_index = self._diagonal_path_index
            shape_only_index = self._diagonal_shape_only_index
        else:
            if not self._path_index_built:
                self._build_path_index()
            path_index = self._path_index
            shape_only_index = self._shape_only_index

        lookup = (
            _normalize_shape_token(shape),
            _normalize_tolerance_token(tolerance),
        )
        candidate = path_index.get(lookup)
        if candidate is None:
            candidate = shape_only_index.get(_normalize_shape_token(shape))
        if candidate is not None and candidate.is_file():
            loaded = Image.open(candidate).convert("RGBA")
            alpha = loaded.getchannel("A")
            alpha_extrema = alpha.getextrema()
            if alpha_extrema == (255, 255):
                loaded = _remove_uniform_background(loaded)
            self._base_cache[key] = loaded
            return loaded

        self._base_cache[key] = None
        return None

    def _load_base_image(self, shape: str, tolerance: str, prefer_diagonal: bool = False) -> Tuple[Any, bool]:
        if prefer_diagonal and self.diagonal_image_dir is not None:
            diagonal_image = self._load_base_image_from_index(shape, tolerance, use_diagonal=True)
            if diagonal_image is not None:
                return diagonal_image, True

        return self._load_base_image_from_index(shape, tolerance, use_diagonal=False), False

    def get_photoimage(self, shape: str, tolerance: str, orientation: str = "0°", size: int = 60) -> Any:
        if Image is None or ImageTk is None:
            return None
        angle = _parse_orientation_degrees(orientation)
        use_diagonal = angle % 90 == 45
        base, used_diagonal_source = self._load_base_image(shape, tolerance, prefer_diagonal=use_diagonal)
        if base is None:
            return None
        cache_key = (shape, tolerance, angle, size)
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]

        img = base.copy()
        render_angle = (angle - 45) % 360 if used_diagonal_source else angle
        if render_angle:
            rotate_kwargs = {"expand": True}
            if hasattr(Image, "Resampling"):
                rotate_kwargs["resample"] = Image.Resampling.BICUBIC
            else:
                rotate_kwargs["resample"] = Image.BICUBIC
            try:
                img = img.rotate(-render_angle, fillcolor=(0, 0, 0, 0), **rotate_kwargs)
            except TypeError:
                img = img.rotate(-render_angle, **rotate_kwargs)

        if hasattr(Image, "Resampling"):
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
        else:
            img.thumbnail((size, size), Image.LANCZOS)

        canvas_image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        offset = ((size - img.width) // 2, (size - img.height) // 2)
        canvas_image.paste(img, offset, img)

        photo = ImageTk.PhotoImage(canvas_image)
        self._photo_cache[cache_key] = photo
        return photo

def random_order(items: List[Any]) -> List[Any]:
    return random.sample(items, len(items))

def random_tolerance_pair() -> Tuple[str, str]:
    pairs = [("3 mm", "1 mm"), ("3 mm", "0.2 mm"), ("1 mm", "0.2 mm")]
    return random.choice(pairs)

def _new_seed_value() -> int:
    return random.randint(100000, 999999999)

def _attach_scenario_seed(scenario: Dict[str, Any], seed: int) -> Dict[str, Any]:
    scenario["scenario_seed"] = int(seed)
    return scenario

def ensure_distinct_order(first: List[str], second: List[str]) -> List[str]:
    if first != second:
        return second
    second = random_order(first)
    while second == first:
        second = random_order(first)
    return second

def build_grid_assignment() -> Tuple[List[List[str]], Dict[str, List[str]]]:
    shape_order = random_order(SHAPES)
    border_positions = GRID_POSITIONS.copy()
    random.shuffle(border_positions)
    selected = border_positions[: len(shape_order)]
    grid = [["" for _ in range(3)] for _ in range(3)]
    side_map: Dict[str, List[str]] = {}
    for shape, (_, coords) in zip(shape_order, selected):
        row, col = coords
        grid[row][col] = shape
        if row == 0:
            side = "top"
        elif row == 2:
            side = "bottom"
        elif col == 0:
            side = "left"
        else:
            side = "right"
        side_map.setdefault(side, []).append(shape)
    return grid, side_map

def normalize_base_name(name: str) -> str:
    normalized = name.strip().lower().replace("_", "-")
    alias_map = {
        "empty-base": "base",
        "base": "base",
        "corner-base-1": "corner-base",
        "corner-base-2": "corner-base",
        "corner-base-3": "corner-base",
        "corner-base": "corner-base",
        "line-base": "line-base",
        "cross-base": "cross-base",
    }
    return alias_map.get(normalized, normalized)

def build_row_plan(row_name: str, piece_order: List[str], piece_orientations: Optional[List[str]] = None) -> Dict[str, Any]:
    normalized_order = [normalize_base_name(piece) for piece in piece_order]
    if piece_orientations is None or len(piece_orientations) != len(normalized_order):
        piece_orientations = ["0°" for _ in normalized_order]
    inventory = {base: 3 for base in BASE_CONNECTION_PORTS}
    for piece in normalized_order:
        inventory[piece] = inventory.get(piece, 0) - 1

    pieces: List[Dict[str, Any]] = []
    joints: List[Dict[str, Any]] = []
    steps: List[str] = []

    for idx, piece_type in enumerate(normalized_order, start=1):
        piece_id = f"P{idx}"
        orientation = piece_orientations[idx - 1]
        piece = {
            "id": piece_id,
            "type": piece_type,
            "orientation": orientation,
            "free_ports": BASE_CONNECTION_PORTS.get(piece_type, 1),
        }
        if idx == 1:
            pieces.append(piece)
            steps.append(f"Place {piece_id} ({piece_type}, {orientation}) as row anchor.")
            continue

        parent = None
        for candidate in pieces:
            if candidate["free_ports"] <= 0:
                continue
            if not BASE_CAN_ACCEPT.get(candidate["type"], True):
                continue
            if candidate["type"] == "cross-base" and piece_type == "cross-base":
                continue
            parent = candidate
            break

        if parent is None:
            steps.append(
                f"No valid free-hole connection found for {piece_id} ({piece_type})."
            )
            pieces.append(piece)
            continue

        parent["free_ports"] -= 1
        if piece["free_ports"] > 0:
            piece["free_ports"] -= 1

        joints.append({
            "from": parent["id"],
            "to": piece_id,
        })
        steps.append(
            f"Connect {piece_id} ({piece_type}, {orientation}) into {parent['id']} ({parent['type']}, {parent['orientation']}) using one free hole."
        )
        pieces.append(piece)

    return {
        "row_name": row_name,
        "piece_order": normalized_order,
        "piece_orientations": piece_orientations,
        "inventory_start": {base: 3 for base in BASE_CONNECTION_PORTS},
        "inventory_remaining": inventory,
        "joints": joints,
        "steps": steps,
    }

def _build_task5_side(name: str, pattern: str, entries: List[Tuple[str, int]]) -> Dict[str, Any]:
    positions = TASK5_PATTERNS[pattern].copy()
    random.shuffle(positions)
    base_orientation = "0°"
    placements: List[Dict[str, Any]] = []
    pos_idx = 0
    for shape, count in entries:
        if count > len(TOLERANCES):
            raise ValueError(f"Cannot place shape '{shape}' {count} times with only {len(TOLERANCES)} tolerances.")
        # One piece per tolerance: repeated shape instances must use different tolerances.
        tolerances_for_shape = random.sample(TOLERANCES, count)
        for _ in range(count):
            row, col = positions[pos_idx]
            pos_idx += 1
            tolerance = tolerances_for_shape.pop()
            placements.append(
                {
                    "row": row,
                    "col": col,
                    "shape": shape,
                    "tolerance": tolerance,
                    "orientation": random_orientation(),
                }
            )
    return {
        "name": name,
        "pattern": pattern,
        "base_orientation": base_orientation,
        "placements": placements,
    }

def _task5_pattern_label(pattern: str) -> str:
    labels = {
        "corner_plus_center": "Corners + center",
        "sides_only": "Sides only",
    }
    return labels.get(pattern, pattern)

def draw_shape_icon(
    canvas: Any,
    x: int,
    y: int,
    shape: str,
    size: int = 40,
    fill: str = "#99ccff",
    piece_image: Any = None,
) -> None:
    if piece_image is not None:
        canvas.create_image(x, y, image=piece_image)
        return
    half = size // 2
    if shape == "triangle":
        canvas.create_polygon(x, y - half, x - half, y + half, x + half, y + half, fill=fill, outline="black")
    elif shape == "rectangle":
        canvas.create_rectangle(x - half, y - half, x + half, y + half, fill=fill, outline="black")
    elif shape == "circle":
        canvas.create_oval(x - half, y - half, x + half, y + half, fill=fill, outline="black")
    elif shape == "hexagon":
        points = [
            x, y - half,
            x - half * 0.87, y - half * 0.5,
            x - half * 0.87, y + half * 0.5,
            x, y + half,
            x + half * 0.87, y + half * 0.5,
            x + half * 0.87, y - half * 0.5,
        ]
        canvas.create_polygon(*points, fill=fill, outline="black")
    elif shape == "L-shape":
        canvas.create_rectangle(x - half, y - half, x - half + size * 0.4, y + half, fill=fill, outline="black")
        canvas.create_rectangle(x - half, y, x + half, y + half, fill=fill, outline="black")
    else:
        canvas.create_text(x, y, text=shape, fill="black")

def draw_task_canvas(canvas: Any, scenario: Dict[str, Any], piece_images: Optional[PieceImageStore] = None) -> None:
    canvas.delete("all")
    width = int(canvas.cget("width"))
    height = int(canvas.cget("height"))
    task_id = scenario["task_id"]
    scale = min(width / 1180.0, height / 620.0)
    render_scale = scale * 1.08 if task_id == 5 else scale * 1.62

    def s(value: int) -> int:
        return max(1, int(round(value * render_scale)))

    image_refs: List[Any] = []
    scenario_seed = scenario.get("scenario_seed", "N/A")
    canvas.create_text(s(12), s(12), text=f"Task {task_id}: {scenario['name']}", anchor="nw", font=("Arial", s(9), "bold"))
    canvas.create_text(width // 2, s(24), text=f"Scenary \"{scenario_seed}\"", font=("Arial", s(16), "bold"))

    if task_id == 1:
        canvas.create_text(width // 2, s(60), text=f"Tolerance: {scenario['tolerance']}", font=("Arial", s(11)))
        peg_order = scenario["peg_order"]
        arm_arrow = scenario.get("arm_arrow", {})
        arrow_side = arm_arrow.get("arrow_side", "left")
        arrow_direction = arm_arrow.get("arrow_direction", "right")
        arm_label = arm_arrow.get("arm", "right").capitalize()

        arrow_y = s(92)
        if arrow_side == "right":
            arrow_start = width - s(90)
            arrow_end = width - s(238)
        else:
            arrow_start = s(90)
            arrow_end = s(238)

        # Respect direction even if side and direction are configured separately.
        if arrow_direction == "left" and arrow_start < arrow_end:
            arrow_start, arrow_end = arrow_end, arrow_start
        if arrow_direction == "right" and arrow_start > arrow_end:
            arrow_start, arrow_end = arrow_end, arrow_start

        canvas.create_line(arrow_start, arrow_y, arrow_end, arrow_y, arrow="last", width=max(2, s(2)))
        canvas.create_text((arrow_start + arrow_end) // 2, arrow_y - s(18), text=f"{arm_label} arm", font=("Arial", s(10), "bold"))

        count = len(peg_order)
        step = max(s(132), width // max(1, count + 1))
        x = (width - step * (count - 1)) // 2
        y = s(150)
        for idx, shape in enumerate(peg_order):
            orientation = scenario.get("orientations", {}).get(shape, "0°")
            image = None
            if piece_images:
                image = piece_images.get_photoimage(shape, scenario["tolerance"], orientation, size=s(92))
            draw_shape_icon(canvas, x, y, shape, size=s(74), piece_image=image)
            if image is not None:
                image_refs.append(image)
            if arrow_direction == "left":
                placement_rank = count - idx
            else:
                placement_rank = idx + 1
            canvas.create_text(x, y + s(64), text=f"#{placement_rank} {shape} ({orientation})", font=("Arial", s(11)))
            x += step

    elif task_id == 2:
        y = s(108)
        for tol in scenario["hole_sequence"]:
            orientation = scenario["orientations"][tol]
            image = None
            if piece_images:
                image = piece_images.get_photoimage(scenario["shape"], tol, orientation, size=s(86))
            if image is not None:
                canvas.create_image(s(90), y, image=image)
                image_refs.append(image)
            else:
                draw_shape_icon(canvas, s(90), y, scenario["shape"], size=s(66))
            canvas.create_rectangle(s(152), y - s(28), width - s(152), y + s(28), outline="black", fill="#ffd699")
            canvas.create_text(width // 2, y, text=f"{scenario['shape']} hole ({tol}, orientation={orientation})", font=("Arial", s(12)))
            y += s(102)

    elif task_id == 3:
        canvas.create_text(width // 2, s(60), text="Board assembly layout", font=("Arial", s(11)))
        x_positions = [width // 4, width // 2, 3 * width // 4]
        layout_items = [
            ("left_base", scenario["layout"]["left_base"]),
            ("middle_base", scenario["layout"]["middle_base"]),
            ("right_base", scenario["layout"]["right_base"]),
        ]
        layout_orientations = scenario.get("layout_orientations", {})
        for x, (slot_key, label) in zip(x_positions, layout_items):
            orientation = layout_orientations.get(slot_key, "0°")
            image = None
            if piece_images:
                image = piece_images.get_photoimage(label, "", orientation, size=s(132))
            if image is not None:
                canvas.create_image(x, s(205), image=image)
                image_refs.append(image)
                canvas.create_text(x, s(278), text=f"{label} ({orientation})", font=("Arial", s(10)))
                continue
            canvas.create_rectangle(x - s(82), s(156), x + s(82), s(272), fill="#d0f0c0", outline="black")
            canvas.create_text(x, s(210), text=f"{label}\n{orientation}", font=("Arial", s(10)))

        if scenario.get("row_build_plan"):
            plan_steps = scenario["row_build_plan"].get("steps", [])
            summary = " | ".join(plan_steps[:3])
            canvas.create_text(width // 2, s(320), text=summary, font=("Arial", s(9)))

    elif task_id == 4:
        canvas.create_text(width // 2, s(60), text="Irregular board assembly", font=("Arial", s(11)))
        parts = [
            ("center_left", scenario["layout"]["center_left"], (width // 2 - s(108), s(130), width // 2 + s(108), s(226)), "#d0f0c0"),
            ("center_right", scenario["layout"]["center_right"], (width // 2 - s(108), s(240), width // 2 + s(108), s(336)), "#c0d0ff"),
            ("left_side_piece", scenario["layout"]["left_side_piece"], (width // 2 - s(286), s(158), width // 2 - s(145), s(280)), "#ffd699"),
            ("right_side_piece", scenario["layout"]["right_side_piece"], (width // 2 + s(145), s(158), width // 2 + s(286), s(280)), "#ffd699"),
        ]
        layout_orientations = scenario.get("layout_orientations", {})
        for slot_key, label, rect, fill in parts:
            x0, y0, x1, y1 = rect
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            orientation = layout_orientations.get(slot_key, "0°")
            image = None
            if piece_images:
                image = piece_images.get_photoimage(label, "", orientation, size=min(x1 - x0, y1 - y0))
            if image is not None:
                canvas.create_image(cx, cy, image=image)
                image_refs.append(image)
                canvas.create_text(cx, y1 + s(16), text=f"{label} ({orientation})", font=("Arial", s(10)))
                continue
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="black")
            canvas.create_text(cx, cy, text=f"{label}\n{orientation}", font=("Arial", s(10)))

        if scenario.get("row_build_plan"):
            plan_steps = scenario["row_build_plan"].get("steps", [])
            summary = " | ".join(plan_steps[:4])
            canvas.create_text(width // 2, s(380), text=summary, font=("Arial", s(9)))

    elif task_id == 5:
        if "sides" in scenario:
            sides = scenario["sides"]
            outer_margin = s(64)
            inter_gap = s(64)
            panel_w = max(240, (width - 2 * outer_margin - inter_gap) // 2)
            panel_h = max(280, height - s(200))
            panel_y = s(86)
            panel_x = [outer_margin, outer_margin + panel_w + inter_gap]

            for idx, side in enumerate(sides[:2]):
                px = panel_x[idx]
                py = panel_y
                canvas.create_rectangle(px, py, px + panel_w, py + panel_h, outline="#888")

                side_name = side.get("name", f"Side {idx + 1}")
                pattern_label = _task5_pattern_label(side.get("pattern", ""))
                canvas.create_text(
                    px + panel_w // 2,
                    py + s(18),
                    text=f"{side_name}: {pattern_label}",
                    font=("Arial", s(11), "bold"),
                )

                grid_top = py + s(38)
                max_cell_w = max(40, (panel_w - s(36)) // 3)
                max_cell_h = max(40, (panel_h - s(118)) // 3)
                cell_size = max(40, min(max_cell_w, max_cell_h))
                grid_w = 3 * cell_size
                grid_h = 3 * cell_size
                grid_x = px + (panel_w - grid_w) // 2
                grid_y = grid_top

                placed: Dict[Tuple[int, int], Dict[str, Any]] = {}
                for item in side.get("placements", []):
                    placed[(int(item["row"]), int(item["col"]))] = item

                for r in range(3):
                    for c in range(3):
                        x0 = grid_x + c * cell_size
                        y0 = grid_y + r * cell_size
                        x1 = x0 + cell_size
                        y1 = y0 + cell_size
                        canvas.create_rectangle(x0, y0, x1, y1, outline="black")

                        slot = placed.get((r, c))
                        if slot is None:
                            continue

                        shape = slot["shape"]
                        tolerance = slot["tolerance"]
                        orientation = slot.get("orientation", "0°")
                        image = None
                        if piece_images:
                            image = piece_images.get_photoimage(shape, tolerance, orientation, size=max(20, int(cell_size * 0.72)))
                        if image is not None:
                            canvas.create_image((x0 + x1) // 2, (y0 + y1) // 2 - s(4), image=image)
                            image_refs.append(image)
                            canvas.create_text((x0 + x1) // 2, y1 - s(16), text=tolerance, font=("Arial", s(7)))
                            canvas.create_text((x0 + x1) // 2, y1 - s(6), text=orientation, font=("Arial", s(7)))
                        else:
                            canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2 - s(8), text=shape, font=("Arial", s(8)))
                            canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2 + s(6), text=tolerance, font=("Arial", s(7)))
                            canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2 + s(16), text=orientation, font=("Arial", s(7)))

                count_map: Dict[Tuple[str, str], int] = defaultdict(int)
                for item in side.get("placements", []):
                    count_map[(item["shape"], item["tolerance"])] += 1
                summary = ", ".join(
                    f"{shape} x{count} ({tol})" for (shape, tol), count in sorted(count_map.items())
                )
                canvas.create_text(
                    px + panel_w // 2,
                    min(py + panel_h - s(12), grid_y + grid_h + s(20)),
                    text=summary,
                    font=("Arial", s(8)),
                )
        else:
            grid = scenario["grid"]
            max_cell_w = max(40, (width - s(120)) // 3)
            max_cell_h = max(40, (height - s(190)) // 3)
            cell_size = max(40, min(s(108), max_cell_w, max_cell_h))
            start_x = (width - cell_size * 3) // 2
            start_y = max(s(80), (height - cell_size * 3 - s(80)) // 2)
            for r in range(3):
                for c in range(3):
                    x0 = start_x + c * cell_size
                    y0 = start_y + r * cell_size
                    x1 = x0 + cell_size
                    y1 = y0 + cell_size
                    canvas.create_rectangle(x0, y0, x1, y1, outline="black")
                    if grid[r][c]:
                        shape = grid[r][c]
                        orientation = scenario.get("shape_orientations", {}).get(shape, "0°")
                        tolerance = scenario.get("visual_tolerance", "1 mm")
                        image = None
                        if piece_images:
                            image = piece_images.get_photoimage(shape, tolerance, orientation, size=s(88))
                        if image is not None:
                            canvas.create_image((x0 + x1) // 2, (y0 + y1) // 2 - s(4), image=image)
                            image_refs.append(image)
                            canvas.create_text((x0 + x1) // 2, y1 - s(12), text=orientation, font=("Arial", s(9)))
                        else:
                            canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2 - s(10), text=shape, font=("Arial", s(10)))
                            canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2 + s(12), text=orientation, font=("Arial", s(9)))
            side_text = ", ".join(f"{side}: {', '.join(shapes)}" for side, shapes in scenario["shape_side_assignments"].items())
            canvas.create_text(width // 2, min(height - s(22), start_y + 3 * cell_size + s(30)), text=side_text, font=("Arial", s(11)))

    elif task_id in (6, 7):
        y0 = s(114)
        for label, row in [("Source row", scenario["source_row"]), ("Target row", scenario["target_row"])]:
            canvas.create_text(width // 2, y0 - s(40), text=f"{label} ({row['tolerance']})", font=("Arial", s(12), "bold"))
            shapes = row["shape_order"]
            count = len(shapes)
            left_margin = s(90)
            right_margin = s(90)
            if count <= 1:
                x_positions = [width // 2]
            else:
                usable_width = max(s(300), width - left_margin - right_margin)
                step = usable_width // (count - 1)
                start_x = (width - step * (count - 1)) // 2
                x_positions = [start_x + i * step for i in range(count)]

            # Keep image size proportional to spacing so columns do not overlap.
            if count > 1:
                max_by_spacing = max(s(54), int((x_positions[1] - x_positions[0]) * 0.62))
            else:
                max_by_spacing = s(84)
            image_size = min(s(84), max_by_spacing)
            icon_size = max(s(46), int(image_size * 0.8))

            for shape_x, shape in zip(x_positions, shapes):
                orientation = row.get("orientations", {}).get(shape, "0°")
                image = None
                if piece_images:
                    image = piece_images.get_photoimage(shape, row["tolerance"], orientation, size=image_size)
                draw_shape_icon(canvas, shape_x, y0 + s(38), shape, size=icon_size, piece_image=image)
                if image is not None:
                    image_refs.append(image)
                canvas.create_text(shape_x, y0 + s(86), text=f"{shape} ({orientation})", font=("Arial", s(11)))
            y0 += s(168)

    else:
        canvas.create_text(width // 2, height // 2, text="Visualization not available.")

    # Keep a reference on the canvas so Tkinter does not garbage-collect drawn PhotoImages.
    canvas._piece_image_refs = image_refs

def run_gui(default_image_dir: Optional[str] = None) -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, scrolledtext, ttk
    except ImportError as exc:
        raise RuntimeError("Tkinter is not available in this Python environment.") from exc

    class ScenarioApp(ttk.Frame):
        def __init__(self, parent: tk.Tk) -> None:
            super().__init__(parent)
            self.parent = parent
            self.parent.title("Peg-in-hole Scenario Generator")
            self.parent.geometry("1840x720")
            self.pack(fill="both", expand=True)
            self.piece_images = PieceImageStore(default_image_dir)
            self._build_ui()
            self.scenario: Dict[str, Any] = {}
            self._update_task_1_controls()

        def _build_ui(self) -> None:
            control_frame = ttk.Frame(self)
            control_frame.pack(side="top", fill="x", padx=10, pady=6)

            ttk.Label(control_frame, text="Task:").grid(row=0, column=0, sticky="w")
            self.task_var = tk.IntVar(value=1)
            self.task_combo = ttk.Combobox(control_frame, textvariable=self.task_var, values=[i for i in range(1, 8)], width=5, state="readonly")
            self.task_combo.grid(row=0, column=1, sticky="w", padx=(5, 15))
            self.task_combo.bind("<<ComboboxSelected>>", lambda event: self._update_task_1_controls())

            ttk.Label(control_frame, text="Seed:").grid(row=0, column=2, sticky="w")
            self.seed_var = tk.StringVar()
            ttk.Entry(control_frame, textvariable=self.seed_var, width=10).grid(row=0, column=3, sticky="w", padx=(5, 15))

            ttk.Button(control_frame, text="Generate", command=self.generate).grid(row=0, column=4, sticky="w")
            ttk.Button(control_frame, text="Save JSON", command=self.save_json).grid(row=0, column=5, sticky="w", padx=(10, 0))

            ttk.Label(control_frame, text="Image folder:").grid(row=1, column=0, sticky="w", pady=(8, 0))
            self.image_dir_var = tk.StringVar(value=default_image_dir or "")
            ttk.Entry(control_frame, textvariable=self.image_dir_var, width=75).grid(row=1, column=1, columnspan=4, sticky="we", padx=(5, 5), pady=(8, 0))
            ttk.Button(control_frame, text="Browse", command=self.choose_image_dir).grid(row=1, column=5, sticky="w", pady=(8, 0))

            task_1_settings = ttk.LabelFrame(control_frame, text="Task 1 settings")
            task_1_settings.grid(row=2, column=0, columnspan=6, sticky="we", pady=(10, 0))
            task_1_settings.columnconfigure(1, weight=1)

            ttk.Label(task_1_settings, text="Hole tolerance:").grid(row=0, column=0, sticky="w", padx=(8, 5), pady=6)
            self.task_1_tolerance_var = tk.StringVar(value=TOLERANCES[0])
            self.task_1_tolerance_combo = ttk.Combobox(
                task_1_settings,
                textvariable=self.task_1_tolerance_var,
                values=TOLERANCES,
                width=10,
                state="readonly",
            )
            self.task_1_tolerance_combo.grid(row=0, column=1, sticky="w", pady=6)

            ttk.Label(task_1_settings, text="Arm to use:").grid(row=0, column=2, sticky="w", padx=(12, 5), pady=6)
            self.task_1_arm_var = tk.StringVar(value="right")
            self.task_1_arm_combo = ttk.Combobox(
                task_1_settings,
                textvariable=self.task_1_arm_var,
                values=["left", "right"],
                width=8,
                state="readonly",
            )
            self.task_1_arm_combo.grid(row=0, column=3, sticky="w", pady=6)

            ttk.Button(task_1_settings, text="Apply Task 1 settings", command=self._apply_task_1_settings).grid(
                row=0,
                column=4,
                sticky="e",
                padx=(16, 8),
                pady=6,
            )

            if Image is None or ImageTk is None:
                ttk.Label(control_frame, text="Pillow not installed: using shape icons only.", foreground="#9a5800").grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))

            self.canvas = tk.Canvas(self, width=1780, height=820, bg="white")
            self.canvas.pack(side="top", padx=10, pady=4)

            self.text = scrolledtext.ScrolledText(self, height=4, wrap="word")
            self.text.pack(fill="x", expand=False, padx=10, pady=(0, 6))

            self.generate()

        def choose_image_dir(self) -> None:
            path = filedialog.askdirectory(title="Select piece image folder")
            if path:
                self.image_dir_var.set(path)
                self.generate()

        def _apply_task_1_settings(self) -> None:
            if int(self.task_var.get()) == 1:
                self.generate()

        def _update_task_1_controls(self) -> None:
            is_task_1 = int(self.task_var.get()) == 1
            state = "readonly" if is_task_1 else "disabled"
            self.task_1_tolerance_combo.configure(state=state)
            self.task_1_arm_combo.configure(state=state)

        def generate(self) -> None:
            seed: Optional[int] = None
            if self.seed_var.get().strip():
                try:
                    seed = int(self.seed_var.get().strip())
                except ValueError:
                    seed = None
            if seed is None:
                seed = _new_seed_value()
                self.seed_var.set(str(seed))
            random.seed(seed)
            task_id = int(self.task_var.get())
            if task_id == 1:
                self.scenario = generate_task_1(
                    tolerance=self.task_1_tolerance_var.get().strip(),
                    arm=self.task_1_arm_var.get().strip(),
                    seed=seed,
                )
            else:
                self.scenario = generate_scenario(task_id)
            self.scenario = _attach_scenario_seed(self.scenario, seed)
            image_dir = self.image_dir_var.get().strip() or None
            self.piece_images.set_image_dir(image_dir)
            draw_task_canvas(self.canvas, self.scenario, piece_images=self.piece_images)
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, json.dumps(self.scenario, indent=2))

        def save_json(self) -> None:
            if not self.scenario:
                return

            # Capture the scenario canvas before opening any modal dialogs.
            captured_image = self._capture_canvas_image()

            output_parent = filedialog.askdirectory(title="Select export folder")
            if not output_parent:
                return

            task_id = self.scenario.get("task_id", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if task_id == 1:
                scenario_seed = self.scenario.get("scenario_seed", "unknown")
                export_dir = Path(output_parent) / "Task1" / f"scene_{scenario_seed}"
            else:
                export_name = f"task_{task_id}_{timestamp}"
                export_dir = Path(output_parent) / export_name
            export_dir.mkdir(parents=True, exist_ok=True)

            json_path = export_dir / "scenario.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.scenario, f, indent=2)

            image_path = self._export_canvas_image(export_dir, captured_image)

            self.text.delete("1.0", tk.END)
            if image_path is not None:
                self.text.insert(
                    tk.END,
                    f"Exported task data and image to: {export_dir}\n"
                    f"JSON: {json_path}\n"
                    f"Image: {image_path}\n",
                )
            else:
                self.text.insert(
                    tk.END,
                    f"Exported task data to: {export_dir}\n"
                    f"JSON: {json_path}\n"
                    "Image export failed (canvas capture unavailable).\n",
                )
                self.text.insert(tk.END, json.dumps(self.scenario, indent=2))

        def _capture_canvas_image(self) -> Any:
            """Capture the current canvas pixels if supported by the environment."""
            self.parent.update_idletasks()
            self.parent.update()
            if ImageGrab is not None:
                try:
                    x0 = self.canvas.winfo_rootx()
                    y0 = self.canvas.winfo_rooty()
                    x1 = x0 + self.canvas.winfo_width()
                    y1 = y0 + self.canvas.winfo_height()
                    return ImageGrab.grab(bbox=(x0, y0, x1, y1))
                except Exception:
                    return None
            return None

        def _export_canvas_image(self, export_dir: Path, captured_image: Any = None) -> Optional[Path]:
            """Save a previously captured canvas PNG when available, otherwise as PostScript."""
            if captured_image is not None:
                try:
                    png_path = export_dir / "scenario.png"
                    captured_image.save(png_path)
                    return png_path
                except Exception:
                    pass

            # Fallback path for environments without screen capture support.
            try:
                ps_path = export_dir / "scenario.ps"
                self.canvas.postscript(file=str(ps_path), colormode="color")
                return ps_path
            except Exception:
                return None

    root = tk.Tk()
    app = ScenarioApp(root)
    root.mainloop()

def generate_task_1(
    tolerance: Optional[str] = None,
    arm: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    rng: Any = random
    if seed is not None:
        # Include arm so same seed still changes when arm choice changes.
        rng = random.Random(f"{seed}:{arm}")

    if tolerance not in TOLERANCES:
        tolerance = rng.choice(TOLERANCES)
    if arm not in {"left", "right"}:
        arm = rng.choice(["left", "right"])

    peg_sequence = rng.sample(SHAPES, len(SHAPES))
    orientations = {shape: rng.choice(ORIENTATIONS) for shape in peg_sequence}
    if arm == "right":
        arm_arrow = {
            "arm": "right",
            "arrow_side": "left",
            "arrow_direction": "right",
        }
        placement_order = peg_sequence.copy()
    else:
        arm_arrow = {
            "arm": "left",
            "arrow_side": "left",
            "arrow_direction": "right",
        }
        placement_order = list(reversed(peg_sequence))
    return {
        "task_id": 1,
        "name": "Same tolerance, different shapes",
        "description": "One tolerance with every shape in a fixed insertion order directed by arm arrow.",
        "tolerance": tolerance,
        "peg_order": peg_sequence,
        "arm_arrow": arm_arrow,
        "placement_order": placement_order,
        "orientations": orientations,
        "notes": [
            "Order is established before data collection and kept during execution.",
            "Use one peg per shape in the chosen fixed order.",
            "The arm arrow indicates which arm to use and the direction of insertion.",
        ],
    }

def generate_task_2() -> Dict[str, Any]:
    shape = random.choice(SHAPES)
    tolerance_sequence = ["3 mm", "1 mm", "0.2 mm"]
    orientation = {tol: random.choice(ORIENTATIONS) for tol in tolerance_sequence}
    return {
        "task_id": 2,
        "name": "Decreasing tolerance",
        "description": "One shape inserted through holes with decreasing tolerance and randomized orientation.",
        "shape": shape,
        "hole_sequence": tolerance_sequence,
        "orientations": orientation,
        "notes": [
            "Use the same shape for all three tolerance holes.",
            "Place the holes in decreasing order of tolerance and randomize the orientation.",
        ],
    }

def generate_task_3() -> Dict[str, Any]:
    left_piece = random.choice(["corner-base", "line-base"])
    right_piece = random.choice(["corner-base", "line-base"])
    layout_types = {
        "middle_base": "base",
        "left_base": left_piece,
        "right_base": right_piece,
    }
    required_edges = [
        ("middle_base", "west", "left_base", "east"),
        ("middle_base", "east", "right_base", "west"),
    ]
    allowed_orientations_by_slot: Dict[str, List[str]] = {}
    if left_piece == "line-base":
        allowed_orientations_by_slot["left_base"] = ["0°", "180°"]
    if right_piece == "line-base":
        allowed_orientations_by_slot["right_base"] = ["0°", "180°"]
    layout_orientations = find_valid_layout_orientations(
        layout_types,
        required_edges,
        allowed_orientations_by_slot=allowed_orientations_by_slot,
    )
    row_build_plan = build_layout_connection_plan("task3_main_row", layout_types, layout_orientations, required_edges)
    return {
        "task_id": 3,
        "name": "Build the board",
        "description": "Assemble one base with two side bases (corner or line) using two arms.",
        "layout": {
            "left_base": left_piece,
            "middle_base": "base",
            "right_base": right_piece,
        },
        "layout_orientations": layout_orientations,
        "row_build_plan": row_build_plan,
        "assembly_sequence": [
            "Hold the base with one arm.",
            "Grab the right side base and insert it to the right of the base.",
            "Switch the holding arm.",
            "Grab the left side base and insert it to the left of the base.",
        ],
    }

def generate_task_4() -> Dict[str, Any]:
    left_side = random.choice(["corner-base", "cross-base"])
    right_side = random.choice(["corner-base", "cross-base"])
    layout_types = {
        "center_left": "base",
        "center_right": "line-base",
        "right_side_piece": right_side,
        "left_side_piece": left_side,
    }
    required_edges = [
        ("center_left", "south", "center_right", "north"),
        ("center_left", "east", "right_side_piece", "west"),
        ("center_left", "west", "left_side_piece", "east"),
    ]
    layout_orientations = find_valid_layout_orientations(layout_types, required_edges)
    row_build_plan = build_layout_connection_plan("task4_irregular_row", layout_types, layout_orientations, required_edges)
    return {
        "task_id": 4,
        "name": "Build the board (irregular shape)",
        "description": "Assemble an empty base, a line base, and two side pieces for an irregular board.",
        "layout": {
            "left_side_piece": left_side,
            "center_left": "base",
            "center_right": "line-base",
            "right_side_piece": right_side,
        },
        "layout_orientations": layout_orientations,
        "row_build_plan": row_build_plan,
        "assembly_sequence": [
            "Join the empty base and the line base.",
            "Attach a corner or cross base on the right side using one hole per piece.",
            "Repeat the same connection on the left side.",
        ],
    }

def generate_task_5() -> Dict[str, Any]:
    shuffled_shapes = random_order(SHAPES)
    shapes_for_4 = shuffled_shapes[:2]
    shapes_for_5 = shuffled_shapes[2:5]

    side_with_4 = _build_task5_side(
        "Top face",
        "sides_only",
        [
            (shapes_for_4[0], 2),
            (shapes_for_4[1], 2),
        ],
    )
    side_with_5 = _build_task5_side(
        "Bottom face",
        "corner_plus_center",
        [
            (shapes_for_5[0], 2),
            (shapes_for_5[1], 2),
            (shapes_for_5[2], 1),
        ],
    )

    if random.choice([True, False]):
        sides = [side_with_4, side_with_5]
    else:
        side_with_5["name"] = "Top face"
        side_with_4["name"] = "Bottom face"
        sides = [side_with_5, side_with_4]

    return {
        "task_id": 5,
        "name": "Rotate the board",
        "description": "Show both board sides at once: one follows a sides-only pattern (4 holes) and the other follows a corners+center pattern (5 holes).",
        "sides": sides,
        "notes": [
            "One side uses 4 holes with 2 shapes (2 pieces each) and 2 tolerances.",
            "The other side uses 5 holes with the remaining 3 shapes in a 2,2,1 distribution.",
            "At most 3 different shapes are used per side.",
        ],
    }

def generate_task_6() -> Dict[str, Any]:
    high_tolerance, low_tolerance = random_tolerance_pair()
    source_shapes = random_order(SHAPES)
    target_shapes = ensure_distinct_order(source_shapes, random_order(SHAPES))
    return {
        "task_id": 6,
        "name": "Decrease of tolerance",
        "description": "Move pegs from a higher tolerance row to a lower tolerance row in a randomized shape arrangement.",
        "source_row": {
            "tolerance": high_tolerance,
            "shape_order": source_shapes,
            "orientations": {shape: random_orientation() for shape in source_shapes},
        },
        "target_row": {
            "tolerance": low_tolerance,
            "shape_order": target_shapes,
            "orientations": {shape: random_orientation() for shape in target_shapes},
        },
        "notes": [
            "Shapes in each row are randomized.",
            "The robot begins with pegs on the higher tolerance row and relocates them to the lower tolerance row.",
        ],
    }

def generate_task_7() -> Dict[str, Any]:
    high_tolerance, low_tolerance = random_tolerance_pair()
    source_shapes = random_order(SHAPES)
    target_shapes = ensure_distinct_order(source_shapes, random_order(SHAPES))
    return {
        "task_id": 7,
        "name": "Increase of tolerance",
        "description": "Move pegs from a lower tolerance row to a higher tolerance row in a randomized shape arrangement.",
        "source_row": {
            "tolerance": low_tolerance,
            "shape_order": source_shapes,
            "orientations": {shape: random_orientation() for shape in source_shapes},
        },
        "target_row": {
            "tolerance": high_tolerance,
            "shape_order": target_shapes,
            "orientations": {shape: random_orientation() for shape in target_shapes},
        },
        "notes": [
            "Shapes in each row are randomized.",
            "The robot begins with pegs on the lower tolerance row and relocates them to the higher tolerance row.",
        ],
    }

def list_tasks() -> List[Dict[str, Any]]:
    return [
        {"id": 1, "name": "Same tolerance, different shapes"},
        {"id": 2, "name": "Decreasing tolerance"},
        {"id": 3, "name": "Build the board"},
        {"id": 4, "name": "Build the board (irregular shape)"},
        {"id": 5, "name": "Rotate the board"},
        {"id": 6, "name": "Decrease of tolerance"},
        {"id": 7, "name": "Increase of tolerance"},
    ]

def generate_scenario(task_id: int) -> Dict[str, Any]:
    generator = {
        1: generate_task_1,
        2: generate_task_2,
        3: generate_task_3,
        4: generate_task_4,
        5: generate_task_5,
        6: generate_task_6,
        7: generate_task_7,
    }
    if task_id not in generator:
        raise ValueError(f"Unsupported task_id={task_id}. Choose 1-7.")
    return generator[task_id]()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate random peg-in-hole benchmark scenarios.")
    parser.add_argument("--task", type=int, choices=range(1, 8), help="Task ID to generate (1-7).")
    parser.add_argument("--count", type=int, default=1, help="Number of random scenarios to generate.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for repeatable scenarios.")
    parser.add_argument("--output", type=str, default=None, help="Write the generated scenario JSON to this file.")
    parser.add_argument("--gui", action="store_true", help="Launch the scenario generator GUI.")
    parser.add_argument("--image-dir", type=str, default=DEFAULT_IMAGE_DIR, help="Folder containing piece images named Shape_Tolerance.jpg.")
    parser.add_argument("--list-tasks", action="store_true", help="Show available tasks and exit.")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if args.gui:
        run_gui(args.image_dir)
        return
    if args.list_tasks:
        print(json.dumps(list_tasks(), indent=2))
        return
    if args.task is None:
        raise SystemExit("Please specify --task with a task ID between 1 and 7.")
    scenarios: List[Dict[str, Any]] = []
    if args.count <= 0:
        raise SystemExit("--count must be a positive integer.")

    if args.seed is not None:
        seed_stream = random.Random(args.seed)
        scenario_seeds = [args.seed] if args.count == 1 else [seed_stream.randint(100000, 999999999) for _ in range(args.count)]
    else:
        scenario_seeds = [_new_seed_value() for _ in range(args.count)]

    for scenario_seed in scenario_seeds:
        random.seed(scenario_seed)
        scenario = generate_scenario(args.task)
        scenarios.append(_attach_scenario_seed(scenario, scenario_seed))

    output = scenarios[0] if args.count == 1 else scenarios
    text = json.dumps(output, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.count} scenario(s) to {args.output}")
    else:
        print(text)

if __name__ == "__main__":
    main()
