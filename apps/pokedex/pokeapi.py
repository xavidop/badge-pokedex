"""PokeAPI data for the Pokedex: the bundled core table and the live species record.

Every Pokemon's stats, types, size and generation ship with the app in
assets/core.bin, built from PokeAPI's own CSV tables, so the list and stats
work without a connection. Scanning an entry fetches its species record for
the dex text, genus and habitat, and its sprite from the PokeAPI sprites repo.

A species record holds every language, so it is scanned as bytes: a str with
non-ASCII text makes MicroPython walk the UTF-8 for each index, which turned a
30KB parse into over a second.
"""

import json
import struct

API = "https://pokeapi.co/api/v2/"
SPRITES = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/"

HEAD_BYTES = 512

# type ids as PokeAPI numbers them (types.csv), index 0 unused
TYPE_NAMES = (
    "", "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost",
    "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
    "dark", "fairy", "stellar",
)

# one record per Pokemon: height, weight, base experience, generation,
# two type ids (0 for none), six base stats in PokeAPI stat order
CORE_FORMAT = "<HHHBBBBBBBBB"
CORE_SIZE = struct.calcsize(CORE_FORMAT)

GENERATIONS = {
    "generation-i": 1, "generation-ii": 2, "generation-iii": 3,
    "generation-iv": 4, "generation-v": 5, "generation-vi": 6,
    "generation-vii": 7, "generation-viii": 8, "generation-ix": 9,
}


def species_url(number):
    return API + "pokemon-species/" + str(number)


def sprite_url(number, shiny=False):
    return SPRITES + ("shiny/" if shiny else "") + str(number) + ".png"


class Core:
    """The bundled table; get(number) never fails, it just reports unknowns."""

    def __init__(self, path, total):
        self.data = b""
        try:
            with open(path, "rb") as handle:
                self.data = handle.read()
        except OSError as error:
            print("Pokedex: no core table:", error)
        self.total = min(total, len(self.data) // CORE_SIZE)

    def get(self, number):
        if not 1 <= number <= self.total:
            return {"height": 0, "weight": 0, "exp": 0, "gen": 0, "types": ["unknown"], "stats": [0] * 6}
        values = struct.unpack_from(CORE_FORMAT, self.data, (number - 1) * CORE_SIZE)
        types = [TYPE_NAMES[values[4]] if values[4] < len(TYPE_NAMES) else "unknown"]
        if values[5]:
            types.append(TYPE_NAMES[values[5]] if values[5] < len(TYPE_NAMES) else "unknown")
        return {
            "height": values[0], "weight": values[1], "exp": values[2], "gen": values[3],
            "types": types, "stats": list(values[6:12]),
        }


def _after(text, key, start=0):
    index = text.find(key, start)
    return -1 if index < 0 else index + len(key)


def _number(text, key, start=0):
    """The integer after '"key":', or None when absent or not a number."""
    index = _after(text, b'"' + key + b'":', start)
    if index < 0:
        return None
    end = index
    while end < len(text) and (48 <= text[end] <= 57 or text[end] == 45):
        end += 1
    try:
        return int(text[index:end])
    except ValueError:
        return None


def _flag(text, key):
    return (b'"' + key + b'":true') in text


def _named(text, key, start=0):
    """The name inside '"key":{"name":"..."}', or None when null or absent."""
    index = _after(text, b'"' + key + b'":{"name":"', start)
    if index < 0:
        return None
    end = text.find(b'"', index)
    return text[index:end].decode() if end > index else None


def _array(text, key, start=0):
    """The flat array after '"key":[' (its entries hold no arrays), and where it ends."""
    index = _after(text, b'"' + key + b'":[', start)
    if index < 0:
        return None, -1
    end = text.find(b"]", index)
    if end < 0:
        return None, -1
    try:
        return json.loads(text[index - 1:end + 1].decode()), end
    except ValueError:
        return None, -1


def _string_end(text, start):
    """Index of the quote closing the JSON string that starts at `start`."""
    index = start
    while True:
        index = text.find(b'"', index)
        if index < 0:
            return -1
        slashes = 0
        back = index - 1
        while back >= start and text[back] == 92:
            slashes += 1
            back -= 1
        if slashes % 2 == 0:
            return index
        index += 1


def _ascii(text):
    out = []
    for char in text:
        code = ord(char)
        if char == "é":
            out.append("e")
        elif 32 <= code < 127:
            out.append(char)
        elif char in "\n\f\r\t":
            out.append(" ")
    return "".join(out)


def clean_flavor(text):
    text = _ascii(text).replace("POKEMON", "Pokemon").replace("POKeMON", "Pokemon")
    return " ".join(text.split())


def _flavor(text):
    """The newest English flavour text, cleaned, or None."""
    start = _after(text, b'"flavor_text_entries":[')
    if start < 0:
        return None
    stop = text.find(b"]", start)
    best = None
    position = start
    while True:
        index = _after(text, b'"flavor_text":"', position)
        if index < 0 or index > stop:
            break
        end = _string_end(text, index)
        if end < 0:
            break
        language = _named(text, b"language", end)
        if language == "en":
            try:
                best = json.loads('"' + text[index:end].decode() + '"')
            except ValueError:
                pass
        position = end + 1
    return clean_flavor(best) if best else None


def _genus(text):
    genera, _ = _array(text, b"genera")
    if not genera:
        return None
    for entry in genera:
        try:
            if entry["language"]["name"] == "en":
                return _ascii(entry["genus"])
        except (KeyError, TypeError):
            pass
    return None


def read_species(path):
    """The fields of a pokemon-species/{id} record saved at `path`."""
    with open(path, "rb") as handle:
        text = handle.read()
    head = text[:HEAD_BYTES]
    record = {
        "genus": _genus(text),
        "flavor": _flavor(text),
        "color": _named(text, b"color"),
        "habitat": _named(text, b"habitat"),
        "shape": _named(text, b"shape"),
        "gen": GENERATIONS.get(_named(text, b"generation"), 0),
        "capture": _number(head, b"capture_rate"),
        "legendary": _flag(head, b"is_legendary"),
        "mythical": _flag(head, b"is_mythical"),
        "baby": _flag(head, b"is_baby"),
    }
    if record["flavor"] is None:
        raise ValueError("species record has no English entry")
    return record
