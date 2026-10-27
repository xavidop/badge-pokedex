"""
An 8-bit Pokedex for all 1025 Pokemon, scanned live from PokeAPI.

Browse the list, open an entry to scan it over Wi-Fi, then flip through its
sprite and facts, base stats, and dex text. Scanned entries stay on the badge.

Controls:
* Up / Down = Move through the list (hold to scroll fast)
* Left / Right = Jump ten entries, or the previous / next Pokemon when open
* Select = Open an entry, or switch it to its shiny sprite
* Menu = Random Pokemon
* Back = Close the entry
"""

import json
import math
import os
import random
import sys

import fetch
import missing_details
from badgeware import State

APP_DIR = "/system/apps/pokedex"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import pokeapi  # noqa: E402  (needs the app directory on the path)

badge.mode(HIRES | VSYNC)
screen.antialias = image.OFF

WIDTH, HEIGHT = screen.width, screen.height
TOTAL = 1025

CACHE_DIR = "/state/pokedex"
TEMP_FILE = CACHE_DIR + "/download.tmp"
CACHE_LIMIT = 80            # scanned entries kept on the badge
NEED_FREE = 160 * 1024      # room a species record needs while it streams in
RETRY_MS = 15000
HEADERS = {"User-Agent": "GitHub Universe Badge 2026 Pokedex"}

SPLASH_MS = 1800
REST_MS = 150               # how long the cursor rests before a preview loads
REPEAT_FIRST_MS = 380
REPEAT_MS = 70
REPEAT_FAST_MS = 28
REPEAT_FAST_AFTER_MS = 1400

# the 8-bit palette: a red casing around a dark panel with cream type
RED = color.rgb(216, 40, 48)
RED_DARK = color.rgb(136, 20, 28)
RED_LIGHT = color.rgb(248, 120, 120)
INK = color.rgb(24, 28, 40)
INK_DARK = color.rgb(10, 12, 20)
INK_LIGHT = color.rgb(44, 50, 70)
CREAM = color.rgb(240, 232, 208)
CREAM_DIM = color.rgb(150, 146, 130)
YELLOW = color.rgb(248, 208, 48)
GREEN = color.rgb(96, 208, 96)
CYAN = color.rgb(96, 208, 232)
LENS = color.rgb(72, 160, 248)
LENS_DARK = color.rgb(24, 72, 160)
WHITE = color.rgb(255, 255, 255)

TITLE = font.futile          # 24px chunky heading
NUMBER = font.ignore         # 28px for dex numbers
BODY = font.nope             # 13px body text
SMALL = font.sins            # 12px labels and hints

TYPE_COLORS = {
    "normal": (168, 168, 120), "fire": (240, 128, 48), "water": (104, 144, 240),
    "electric": (248, 208, 48), "grass": (120, 200, 80), "ice": (152, 216, 216),
    "fighting": (192, 48, 40), "poison": (160, 64, 160), "ground": (224, 192, 104),
    "flying": (168, 144, 240), "psychic": (248, 88, 136), "bug": (168, 184, 32),
    "rock": (184, 160, 56), "ghost": (112, 88, 152), "dragon": (112, 56, 248),
    "dark": (112, 88, 72), "steel": (184, 184, 208), "fairy": (238, 153, 172),
    "stellar": (64, 180, 200), "unknown": (104, 160, 144),
}
TYPE_PENS = {}
TYPE_INKS = {}
for _name, (_r, _g, _b) in TYPE_COLORS.items():
    TYPE_PENS[_name] = color.rgb(_r, _g, _b)
    TYPE_INKS[_name] = INK_DARK if _r * 299 + _g * 587 + _b * 114 > 140000 else WHITE

STAT_LABELS = ("HP", "ATK", "DEF", "SP.A", "SP.D", "SPD")
ROMAN = ("?", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")
PAGES = ("INFO", "STATS", "DEX")

# a 16x16 Pokeball drawn with rectangles, for the splash
BALL = (
    ".....XXXXXX.....",
    "...XXRRRRRRXX...",
    "..XRLLRRRRRRRX..",
    ".XRLRRRRRRRRRRX.",
    ".XRRRRRRRRRRRRX.",
    "XRRRRRRRRRRRRRRX",
    "XRRRRRXXXXRRRRRX",
    "XXXXXXWWWWXXXXXX",
    "XXXXXXWWWWXXXXXX",
    "XWWWWWXXXXWWWWWX",
    "XWWWWWWWWWWWWWWX",
    ".XWWWWWWWWWWWWX.",
    ".XWWWWWWWWWWWWX.",
    "..XWWWWWWWWWWX..",
    "...XXWWWWWWXX...",
    ".....XXXXXX.....",
)
BALL_PENS = {"X": INK_DARK, "R": RED, "L": RED_LIGHT, "W": CREAM}

# a 5x5 mark for entries already scanned
MARK = (
    ".XXX.",
    "XRRRX",
    "XXXXX",
    "XWWWX",
    ".XXX.",
)
MARK_PENS = {"X": INK_DARK, "R": RED, "W": CREAM}

# the list: rows on the left, a preview card on the right
LIST_LEFT, LIST_TOP, LIST_W = 8, 28, 186
ROW_H = 17
ROWS = 11
CARD_LEFT, CARD_TOP, CARD_W, CARD_H = 200, 28, 112, 190

SPLASH, LIST, ENTRY = 0, 1, 2

try:
    os.mkdir(CACHE_DIR)
except OSError:
    pass


# ----------------------------------------------------------------------------
# bundled data and saved state

def load_names():
    """Line N of assets/names.txt is the name of Pokemon number N."""
    names = [""]
    try:
        with open("assets/names.txt") as handle:
            for line in handle:
                names.append(line.strip().upper())
    except OSError:
        pass
    while len(names) <= TOTAL:
        names.append("???")
    return names


NAMES = load_names()
CORE = pokeapi.Core("assets/core.bin", TOTAL)

state = {"seen": [], "cache": [], "last": 1}
State.load("pokedex", state)


def tidy_state():
    """Saved values can come back with any type; keep only what makes sense."""
    for key in ("seen", "cache"):
        values = state.get(key)
        clean = []
        if isinstance(values, list):
            for value in values:
                if isinstance(value, int) and 1 <= value <= TOTAL and value not in clean:
                    clean.append(value)
        state[key] = clean
    last = state.get("last")
    state["last"] = last if isinstance(last, int) and 1 <= last <= TOTAL else 1


tidy_state()


def save_state():
    try:
        State.save("pokedex", state)
    except OSError as error:
        print("Pokedex: could not save state:", error)


# ----------------------------------------------------------------------------
# the cache of scanned entries under /state/pokedex

def entry_path(number, suffix):
    return "%s/%d%s" % (CACHE_DIR, number, suffix)


def remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass


def is_scanned(number):
    return file_exists(entry_path(number, ".json"))


def load_dex(number):
    """The saved species record for a scanned entry, or None when absent or damaged."""
    path = entry_path(number, ".json")
    if not file_exists(path):
        return None
    try:
        with open(path) as handle:
            record = json.load(handle)
        if not isinstance(record, dict) or not isinstance(record.get("flavor"), str):
            raise ValueError("incomplete")
        return record
    except (OSError, ValueError):
        forget(number)
        return None


def forget(number):
    for suffix in (".json", ".png", "s.png"):
        remove_file(entry_path(number, suffix))
    if number in state["cache"]:
        state["cache"].remove(number)


def remember(number):
    """Mark an entry as freshly used and drop the oldest beyond the limit."""
    if number in state["cache"]:
        state["cache"].remove(number)
    state["cache"].append(number)
    while len(state["cache"]) > CACHE_LIMIT:
        forget(state["cache"][0])
    if number not in state["seen"]:
        state["seen"].append(number)
    save_state()


def free_space():
    try:
        stats = os.statvfs("/state")
        return stats[0] * stats[3]
    except OSError:
        return NEED_FREE


def make_room():
    """A record streams to flash, so clear old entries until it fits."""
    remove_file(TEMP_FILE)
    while free_space() < NEED_FREE and state["cache"]:
        forget(state["cache"][0])


def load_sprite(number, shiny=False):
    path = entry_path(number, "s.png" if shiny else ".png")
    if not file_exists(path):
        return None
    try:
        return image.load(path)
    except (OSError, ValueError):
        remove_file(path)
        return None


# ----------------------------------------------------------------------------
# scanning: the species record and the sprite, one step a frame

class Scan:
    """Fetch one Pokemon's species record and sprite without blocking frames.

    The firmware's fetch streams to a file and advances every time it is
    tested for truth, so update() pokes it once a frame and moves to the next
    stage when it reports done. Failures wait RETRY_MS and try that stage again.
    """

    LABELS = {"species": "fetching dex entry", "sprite": "fetching sprite", "shiny": "fetching shiny"}

    def __init__(self, number, shiny=False):
        self.number = number
        self.stages = ("shiny",) if shiny else ("species", "sprite")
        self.stage = 0
        self.request = None
        self.error = None
        self.retry_at = 0
        self.status = "starting scan"
        self.done = False
        self.sprite_failed = False
        self.missing = missing_details.missing("WIFI_SSID")

    @property
    def failed(self):
        return self.error is not None

    @property
    def current(self):
        return self.stages[self.stage]

    def target(self):
        if self.current == "species":
            return pokeapi.species_url(self.number), TEMP_FILE
        if self.current == "sprite":
            return pokeapi.sprite_url(self.number), entry_path(self.number, ".png.tmp")
        return pokeapi.sprite_url(self.number, True), entry_path(self.number, "s.png.tmp")

    def finish_stage(self, path):
        if self.current == "species":
            record = pokeapi.read_species(path)
            remove_file(path)
            with open(entry_path(self.number, ".json"), "w") as handle:
                json.dump(record, handle)
            remember(self.number)
        elif self.current == "sprite":
            os.rename(path, entry_path(self.number, ".png"))
        else:
            os.rename(path, entry_path(self.number, "s.png"))

    def fail(self, reason):
        print("Pokedex: %s failed: %s" % (self.current, reason))
        self.request = None
        remove_file(self.target()[1])
        if self.current != "species":
            # a missing sprite is not worth holding the entry for
            self.sprite_failed = True
            self.done = True
            return
        self.error = str(reason)
        self.retry_at = badge.ticks + RETRY_MS

    def retry_now(self):
        self.retry_at = 0

    def update(self):
        if self.done:
            return
        if self.missing:
            self.status = "no wi-fi details"
            self.error = "Add the Wi-Fi name and password in Settings"
            return
        if self.error:
            if badge.ticks < self.retry_at:
                return
            self.error = None
        if self.request is None:
            url, path = self.target()
            if path == TEMP_FILE:
                make_room()
            else:
                remove_file(path)
            self.request = fetch.url(url, headers=HEADERS).to(path)
            self.status = self.LABELS[self.current]
            return
        finished = bool(self.request)
        if self.request.error:
            self.fail(self.request.error)
            return
        if not finished:
            self.status = self.request.state or self.LABELS[self.current]
            return
        try:
            self.finish_stage(self.target()[1])
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.fail(error)
            return
        self.request = None
        self.stage += 1
        if self.stage >= len(self.stages):
            self.done = True
            self.status = "scan complete"


# ----------------------------------------------------------------------------
# an open entry

class Entry:
    def __init__(self, number):
        self.number = number
        self.name = NAMES[number]
        self.core = CORE.get(number)
        self.dex = load_dex(number)
        self.sprite = load_sprite(number)
        self.shiny = None
        self.show_shiny = False
        self.scan = None
        if self.dex is None or self.sprite is None:
            self.scan = Scan(number)
        else:
            remember(number)

    @property
    def scanning(self):
        return self.scan is not None and not self.scan.done and not self.scan.failed

    def toggle_shiny(self):
        if self.show_shiny:
            self.show_shiny = False
            return
        if self.shiny is None:
            self.shiny = load_sprite(self.number, True)
        if self.shiny is None:
            if self.scan is not None and not self.scan.done:
                return
            self.scan = Scan(self.number, shiny=True)
        self.show_shiny = True

    def rescan(self):
        forget(self.number)
        self.dex = None
        self.sprite = None
        self.shiny = None
        self.show_shiny = False
        self.scan = Scan(self.number)

    def update(self):
        if self.scan is None:
            return
        self.scan.update()
        if self.dex is None and is_scanned(self.number):
            self.dex = load_dex(self.number)
        if self.scan.done:
            if self.sprite is None:
                self.sprite = load_sprite(self.number)
            if self.show_shiny and self.shiny is None:
                self.shiny = load_sprite(self.number, True)
                if self.shiny is None:
                    self.show_shiny = False

    def current_sprite(self):
        if self.show_shiny and self.shiny is not None:
            return self.shiny
        return self.sprite


# ----------------------------------------------------------------------------
# drawing helpers

def write(text, x, y, pen, face=BODY):
    screen.font = face
    screen.pen = pen
    screen.text(text, x, y)


def text_width(text, face=BODY):
    screen.font = face
    return screen.measure_text(text)[0]


def write_centred(text, cx, y, pen, face=BODY):
    write(text, cx - text_width(text, face) // 2, y, pen, face)


def write_right(text, right, y, pen, face=BODY):
    write(text, right - text_width(text, face), y, pen, face)


def write_wrapped(text, x, y, w, h, pen, face=BODY):
    screen.font = face
    screen.pen = pen
    screen.text(text, rect(x, y, w, h), align=(LEFT, TOP))


def fill(x, y, w, h, pen):
    screen.pen = pen
    screen.rectangle(x, y, w, h)


def pixel_art(rows, pens, x, y, scale):
    for row, line in enumerate(rows):
        for column, key in enumerate(line):
            pen = pens.get(key)
            if pen is not None:
                fill(x + column * scale, y + row * scale, scale, scale, pen)


def pill(label, x, y, kind):
    """A type badge; returns its width."""
    width = text_width(label, SMALL) + 10
    fill(x, y, width, 14, TYPE_PENS.get(kind, TYPE_PENS["unknown"]))
    write(label, x + 5, y + 1, TYPE_INKS.get(kind, WHITE), SMALL)
    return width


def type_pills(types, x, y):
    for kind in types[:2]:
        x += pill(kind.upper(), x, y, kind) + 4


def sprite_box(sprite, x, y, size):
    """A framed sprite, or a question mark when it has not been fetched."""
    fill(x - 2, y - 2, size + 4, size + 4, INK_DARK)
    fill(x, y, size, size, INK_LIGHT)
    if sprite is not None:
        screen.blit(sprite, rect(0, 0, sprite.width, sprite.height), rect(x, y, size, size), image.NEAREST)
    else:
        write_centred("?", x + size // 2, y + size // 2 - 14, CREAM_DIM, NUMBER)


def draw_casing(title, right_text=None):
    """The red device body: lens and lights on top, panel below, hints bar at the foot."""
    fill(0, 0, WIDTH, HEIGHT, RED)
    fill(0, 23, WIDTH, 2, RED_DARK)
    # the big blue lens with its ring and a highlight
    fill(6, 4, 16, 16, CREAM)
    fill(8, 6, 12, 12, LENS_DARK)
    fill(9, 7, 10, 10, LENS)
    fill(10, 8, 3, 3, WHITE)
    # three little status lights
    for index, pen in enumerate((RED_LIGHT, YELLOW, GREEN)):
        fill(28 + index * 8, 5, 5, 5, INK_DARK)
        fill(29 + index * 8, 6, 3, 3, pen)
    write(title, 56, 6, CREAM, BODY)
    if right_text:
        write_right(right_text, WIDTH - 8, 6, CREAM, BODY)
    fill(4, 24, WIDTH - 8, HEIGHT - 24 - 18, INK_DARK)
    fill(6, 26, WIDTH - 12, HEIGHT - 26 - 20, INK)


def draw_hints(hints):
    """Key hints along the bottom bar."""
    y = HEIGHT - 15
    x = 8
    for key, label in hints:
        fill(x, y, text_width(key, SMALL) + 4, 13, CREAM)
        write(key, x + 2, y, RED_DARK, SMALL)
        x += text_width(key, SMALL) + 7
        write(label, x, y, CREAM, SMALL)
        x += text_width(label, SMALL) + 10


def dex_number(number):
    return "No.%03d" % number


def metres(decimetres):
    return "%d.%d m" % (decimetres // 10, decimetres % 10)


def kilograms(hectograms):
    return "%d.%d kg" % (hectograms // 10, hectograms % 10)


def stat_pen(value):
    if value < 50:
        return RED_LIGHT
    if value < 80:
        return YELLOW
    if value < 110:
        return GREEN
    return CYAN


# ----------------------------------------------------------------------------
# app state

mode = SPLASH
splash_at = None        # set on the first frame, once the badge's clock is running
cursor = state["last"]
cursor_core = CORE.get(cursor)
top = 1
page = 0
entry = None
preview = None          # (number, sprite or None, dex or None) for the list card
rest_since = badge.ticks
light = 0.0


class Repeat:
    """A button that fires once, then repeats while held, faster the longer."""

    def __init__(self, button):
        self.button = button
        self.started = 0
        self.next_at = 0

    def fired(self):
        if badge.pressed(self.button):
            self.started = badge.ticks
            self.next_at = badge.ticks + REPEAT_FIRST_MS
            return True
        if badge.held(self.button) and badge.ticks >= self.next_at:
            fast = badge.ticks - self.started > REPEAT_FAST_AFTER_MS
            self.next_at = badge.ticks + (REPEAT_FAST_MS if fast else REPEAT_MS)
            return True
        return False


up = Repeat(BUTTON_UP)
down = Repeat(BUTTON_DOWN)
left = Repeat(BUTTON_LEFT)
right = Repeat(BUTTON_RIGHT)


def move_cursor(delta):
    global cursor, cursor_core, top, rest_since
    cursor = min(TOTAL, max(1, cursor + delta))
    cursor_core = CORE.get(cursor)
    if cursor < top:
        top = cursor
    elif cursor >= top + ROWS:
        top = cursor - ROWS + 1
    top = min(max(1, TOTAL - ROWS + 1), max(1, top))
    rest_since = badge.ticks
    state["last"] = cursor


def open_entry(number):
    global mode, entry, page
    move_cursor(number - cursor)
    entry = Entry(number)
    page = 0
    mode = ENTRY


def close_entry():
    global mode, entry, preview
    entry = None
    preview = None
    mode = LIST
    save_state()


def update_preview():
    """Load the highlighted entry's sprite once the cursor has rested on it."""
    global preview
    if preview is not None and preview[0] == cursor:
        return
    if badge.ticks - rest_since < REST_MS:
        return
    preview = (cursor, load_sprite(cursor), load_dex(cursor))


def update_lights():
    """The case lights breathe while a scan is running."""
    global light
    scanning = entry is not None and entry.scanning
    target = round(0.12 + 0.12 * math.sin(badge.ticks / 250), 2) if scanning else 0.0
    if target != light:
        light = target
        badge.caselights(light)


# ----------------------------------------------------------------------------
# screens

def draw_splash():
    fill(0, 0, WIDTH, HEIGHT, RED)
    bounce = int(abs(math.sin(badge.ticks / 300)) * 8)
    pixel_art(BALL, BALL_PENS, WIDTH // 2 - 48, 36 - bounce, 6)
    fill(0, 140, WIDTH, 60, INK)
    fill(0, 140, WIDTH, 2, INK_DARK)
    fill(0, 198, WIDTH, 2, INK_DARK)
    write_centred("POKEDEX", WIDTH // 2, 148, CREAM, TITLE)
    write_centred("%d POKEMON  -  %d SEEN" % (TOTAL, len(state["seen"])), WIDTH // 2, 178, YELLOW, SMALL)
    if (badge.ticks // 400) % 2:
        write_centred("PRESS ANY BUTTON", WIDTH // 2, 214, CREAM, BODY)


def draw_list():
    draw_casing("POKEDEX", "SEEN %d/%d" % (len(state["seen"]), TOTAL))
    for row in range(ROWS):
        number = top + row
        if number > TOTAL:
            break
        y = LIST_TOP + row * ROW_H
        selected = number == cursor
        if selected:
            fill(LIST_LEFT, y - 1, LIST_W, ROW_H - 1, CREAM)
        write("%03d" % number, LIST_LEFT + 12, y + 1, RED_DARK if selected else CREAM_DIM, BODY)
        write(NAMES[number], LIST_LEFT + 52, y + 1, INK_DARK if selected else CREAM, BODY)
        if number in state["seen"]:
            pixel_art(MARK, MARK_PENS, LIST_LEFT + 3, y + 4, 1)
    # the scroll track
    track_h = ROWS * ROW_H - 2
    fill(LIST_LEFT + LIST_W + 2, LIST_TOP, 3, track_h, INK_DARK)
    knob = max(6, track_h * ROWS // TOTAL)
    knob_y = LIST_TOP + (track_h - knob) * (top - 1) // max(1, TOTAL - ROWS)
    fill(LIST_LEFT + LIST_W + 2, knob_y, 3, knob, CREAM_DIM)

    # the preview card
    fill(CARD_LEFT, CARD_TOP, CARD_W, CARD_H, INK_LIGHT)
    fill(CARD_LEFT, CARD_TOP, CARD_W, 1, INK_DARK)
    shown = preview if preview is not None and preview[0] == cursor else None
    sprite_box(shown[1] if shown else None, CARD_LEFT + 8, CARD_TOP + 8, 96)
    write_centred(dex_number(cursor), CARD_LEFT + CARD_W // 2, CARD_TOP + 110, YELLOW, SMALL)
    name = NAMES[cursor]
    face = BODY if text_width(name, BODY) <= CARD_W - 8 else SMALL
    write_centred(name, CARD_LEFT + CARD_W // 2, CARD_TOP + 124, CREAM, face)
    type_pills(cursor_core["types"], CARD_LEFT + 8, CARD_TOP + 144)
    if shown and shown[2]:
        write_centred("SCANNED", CARD_LEFT + CARD_W // 2, CARD_TOP + 166, GREEN, SMALL)
    elif cursor in state["seen"]:
        write_centred("SEEN", CARD_LEFT + CARD_W // 2, CARD_TOP + 166, CREAM_DIM, SMALL)
    else:
        write_centred("NOT SCANNED", CARD_LEFT + CARD_W // 2, CARD_TOP + 166, CREAM_DIM, SMALL)
    draw_hints((("^v", "MOVE"), ("<>", "JUMP 10"), ("SEL", "OPEN"), ("MENU", "RANDOM")))


def draw_scan_panel(x, y, w, h):
    """What the scan is doing, in place of the dex text, while an entry loads."""
    scan = entry.scan
    fill(x, y, w, h, INK_LIGHT)
    if scan.failed:
        write("NO WI-FI" if scan.missing else "NO SIGNAL", x + 6, y + 6, RED_LIGHT, BODY)
        write_wrapped(scan.error, x + 6, y + 24, w - 12, h - 44, CREAM, SMALL)
        write("SET UP IN SETTINGS" if scan.missing else "SEL: RETRY NOW", x + 6, y + h - 16, YELLOW, SMALL)
        return
    write("SCANNING", x + 6, y + 6, YELLOW, BODY)
    write_wrapped(scan.status, x + 6, y + 24, w - 12, h - 44, CREAM, SMALL)
    # a strip of blocks sweeping along the bottom of the panel
    blocks = (w - 12) // 8
    lit = (badge.ticks // 90) % blocks
    for index in range(blocks):
        near = abs(index - lit)
        fill(x + 6 + index * 8, y + h - 12, 6, 6, YELLOW if near == 0 else (CREAM_DIM if near == 1 else INK_DARK))


def scan_line():
    """One line on the scan's progress for the pages that show it small."""
    scan = entry.scan
    if scan is None or scan.done:
        return None, None
    if scan.failed:
        return ("NO WI-FI" if scan.missing else "NO SIGNAL - SEL RETRIES"), RED_LIGHT
    dots = "." * (1 + (badge.ticks // 300) % 3)
    return scan.status.upper() + dots, YELLOW


def draw_entry():
    draw_casing(dex_number(entry.number), "SEEN %d/%d" % (len(state["seen"]), TOTAL))
    # page tabs across the top of the panel
    x = 10
    for index, label in enumerate(PAGES):
        width = text_width(label, SMALL) + 10
        if index == page:
            fill(x, 28, width, 14, CREAM)
            write(label, x + 5, 29, INK_DARK, SMALL)
        else:
            write(label, x + 5, 29, CREAM_DIM, SMALL)
        x += width + 4
    if entry.show_shiny and entry.shiny is not None:
        write_right("SHINY", WIDTH - 10, 29, YELLOW, SMALL)

    if page == 0:
        draw_info_page()
    elif page == 1:
        draw_stats_page()
    else:
        draw_dex_page()
    draw_hints((("<>", "PREV/NEXT"), ("^v", "PAGE"), ("SEL", "SHINY"), ("BACK", "LIST")))


def draw_info_page():
    core = entry.core
    dex = entry.dex
    sprite_box(entry.current_sprite(), 12, 48, 160)
    x = 184
    name = entry.name
    face = TITLE if text_width(name, TITLE) <= WIDTH - x - 10 else BODY
    write(name, x, 46, CREAM, face)
    genus = dex.get("genus") if dex else None
    write(genus or "Pokemon", x, 74, CREAM_DIM, SMALL)
    type_pills(core["types"], x, 92)
    rows = (
        ("HT", metres(core["height"])),
        ("WT", kilograms(core["weight"])),
        ("GEN", ROMAN[core["gen"]] if core["gen"] < len(ROMAN) else "?"),
        ("EXP", str(core["exp"]) if core["exp"] else "-"),
    )
    for index, (label, value) in enumerate(rows):
        y = 116 + index * 20
        write(label, x, y, CREAM_DIM, SMALL)
        write(value, x + 36, y - 1, CREAM, BODY)
    line, pen = scan_line()
    if line:
        write_wrapped(line, x, 196, WIDTH - x - 10, 24, pen, SMALL)
    elif dex:
        tags = []
        if dex.get("legendary"):
            tags.append("LEGENDARY")
        if dex.get("mythical"):
            tags.append("MYTHICAL")
        if dex.get("baby"):
            tags.append("BABY")
        if tags:
            write(" ".join(tags), x, 198, YELLOW, SMALL)
    if entry.scan is not None and entry.scan.sprite_failed and entry.sprite is None:
        write("NO SPRITE - SEL RETRIES", 20, 196, RED_LIGHT, SMALL)


def draw_stats_page():
    core = entry.core
    sprite_box(entry.current_sprite(), 12, 48, 96)
    write(entry.name, 12, 150, CREAM, BODY if text_width(entry.name, BODY) <= 100 else SMALL)
    type_pills(core["types"], 12, 168)
    x = 124
    stats = core["stats"]
    for index, value in enumerate(stats):
        y = 50 + index * 24
        write(STAT_LABELS[index], x, y + 1, CREAM_DIM, SMALL)
        write_right(str(value), x + 72, y, CREAM, BODY)
        fill(x + 78, y + 2, 108, 10, INK_DARK)
        fill(x + 80, y + 4, max(2, int(104 * min(value, 255) / 255)), 6, stat_pen(value))
    write("TOTAL", x, 196, CREAM_DIM, SMALL)
    write_right(str(sum(stats)), x + 72, 195, YELLOW, BODY)
    capture = entry.dex.get("capture") if entry.dex else None
    line, pen = scan_line()
    if line:
        short = "NO SIGNAL" if entry.scan.failed else "SCANNING" + line[-3:].replace("G", "")
        write(short, x + 90, 196, pen, SMALL)
    elif capture is not None:
        write("CATCH %d/255" % capture, x + 90, 196, CREAM_DIM, SMALL)


def draw_dex_page():
    x = 12
    dex = entry.dex
    if dex is None:
        draw_scan_panel(x, 48, WIDTH - 24, 160)
        return
    write(entry.name, x, 46, CREAM, BODY)
    write(dex.get("genus") or "", x + text_width(entry.name, BODY) + 10, 47, CREAM_DIM, SMALL)
    fill(x, 62, WIDTH - 24, 1, INK_LIGHT)
    write_wrapped(dex.get("flavor") or "No dex text.", x, 68, WIDTH - 24, 100, CREAM, BODY)
    fill(x, 172, WIDTH - 24, 1, INK_LIGHT)
    facts = []
    if dex.get("habitat"):
        facts.append(("HABITAT", dex["habitat"].upper()))
    if dex.get("shape"):
        facts.append(("SHAPE", dex["shape"].upper()))
    if dex.get("color"):
        facts.append(("COLOR", dex["color"].upper()))
    fx = x
    for label, value in facts[:3]:
        write(label, fx, 180, CREAM_DIM, SMALL)
        write(value, fx, 193, CREAM, BODY)
        fx += max(text_width(label, SMALL), text_width(value, BODY)) + 18


# ----------------------------------------------------------------------------
# input per screen

def update_splash():
    global mode, splash_at
    if splash_at is None:
        splash_at = badge.ticks
    if badge.ticks - splash_at > SPLASH_MS and badge.pressed():
        mode = LIST
    elif badge.ticks - splash_at > SPLASH_MS * 4:
        mode = LIST
    draw_splash()


def update_list():
    if up.fired():
        move_cursor(-1)
    if down.fired():
        move_cursor(1)
    if left.fired():
        move_cursor(-10)
    if right.fired():
        move_cursor(10)
    if badge.pressed(BUTTON_MENU):
        move_cursor(random.randint(1, TOTAL) - cursor)
    if badge.pressed(BUTTON_SELECT):
        open_entry(cursor)
        return
    update_preview()
    draw_list()


def update_entry():
    global page
    if badge.pressed(BUTTON_BACK):
        close_entry()
        return
    if left.fired() and entry.number > 1:
        open_entry(entry.number - 1)
    elif right.fired() and entry.number < TOTAL:
        open_entry(entry.number + 1)
    if badge.pressed(BUTTON_UP):
        page = (page - 1) % len(PAGES)
    if badge.pressed(BUTTON_DOWN):
        page = (page + 1) % len(PAGES)
    if badge.pressed(BUTTON_MENU):
        open_entry(random.randint(1, TOTAL))
    if badge.pressed(BUTTON_SELECT):
        if entry.scan is not None and entry.scan.failed and not entry.scan.missing:
            entry.scan.retry_now()
        elif entry.scan is not None and entry.scan.done and entry.sprite is None:
            entry.rescan()
        else:
            entry.toggle_shiny()
    entry.update()
    draw_entry()


def update():
    if mode == SPLASH:
        update_splash()
    elif mode == LIST:
        update_list()
    else:
        update_entry()
    update_lights()


def on_exit():
    badge.caselights(0)
    save_state()


random.seed(badge.ticks)
remove_file(TEMP_FILE)
move_cursor(0)
run(update)
