"""Rebuild apps/pokedex/assets/{names.txt,core.bin} from PokeAPI's CSV tables.

Downloads the tables from the PokeAPI repository, then writes one name per line
(ASCII only, line N = Pokemon N) and one 15-byte record per Pokemon holding
height, weight, base experience, generation, two type ids and six base stats.

    python3 tools/build_data.py
"""
import csv
import io
import struct
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "pokedex"))
import pokeapi  # noqa: E402

CSV = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
TOTAL = 1025
ENGLISH = "9"


def table(name):
    with urllib.request.urlopen(CSV + name + ".csv") as reply:
        return list(csv.DictReader(io.TextIOWrapper(reply, encoding="utf-8")))


def ascii_name(name):
    return (name.replace("♀", " F").replace("♂", " M")
            .replace("’", "'").replace("é", "e"))


def main():
    assets = Path(__file__).resolve().parents[1] / "apps" / "pokedex" / "assets"
    types = {int(row["id"]): row["identifier"] for row in table("types")}
    for index in range(1, len(pokeapi.TYPE_NAMES)):
        assert types[index] == pokeapi.TYPE_NAMES[index], (index, types[index])

    names = {}
    for row in table("pokemon_species_names"):
        if row["local_language_id"] == ENGLISH and int(row["pokemon_species_id"]) <= TOTAL:
            names[int(row["pokemon_species_id"])] = ascii_name(row["name"])
    assert all(names[n].isascii() for n in range(1, TOTAL + 1))
    (assets / "names.txt").write_text("".join(names[n] + "\n" for n in range(1, TOTAL + 1)))

    generation = {int(row["id"]): int(row["generation_id"]) for row in table("pokemon_species")}
    pokemon = {int(row["id"]): row for row in table("pokemon") if int(row["id"]) <= TOTAL}
    stats, kinds = {}, {}
    for row in table("pokemon_stats"):
        if int(row["pokemon_id"]) <= TOTAL:
            stats.setdefault(int(row["pokemon_id"]), {})[int(row["stat_id"])] = int(row["base_stat"])
    for row in table("pokemon_types"):
        if int(row["pokemon_id"]) <= TOTAL:
            kinds.setdefault(int(row["pokemon_id"]), {})[int(row["slot"])] = int(row["type_id"])

    out = bytearray()
    for number in range(1, TOTAL + 1):
        entry, base, slots = pokemon[number], stats[number], kinds[number]
        assert int(entry["species_id"]) == number and sorted(base) == [1, 2, 3, 4, 5, 6]
        out += struct.pack(pokeapi.CORE_FORMAT, int(entry["height"]), int(entry["weight"]),
                           int(entry["base_experience"] or 0), generation[number],
                           slots[1], slots.get(2, 0), *[base[i] for i in range(1, 7)])
    (assets / "core.bin").write_bytes(out)
    print("names.txt and core.bin written for", TOTAL, "Pokemon")


if __name__ == "__main__":
    main()
