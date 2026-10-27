# Pokedex

An 8-bit Pokedex for all 1025 Pokemon that scans each entry live from PokeAPI over Wi-Fi.

Browse the list, open an entry to scan it, then flip through its sprite and
facts, base stats, and dex text. Every entry you scan is kept on the badge, so
it opens again without a connection, and the Pokedex counts how many you have
seen.

## Controls

* Up / Down: move through the list (hold to scroll fast)
* Left / Right: jump ten entries in the list, or step to the previous or next
  Pokemon when an entry is open
* Select: open the highlighted entry; when an entry is open, switch between its
  normal and shiny sprite
* Menu: jump to a random Pokemon
* Back: close the entry and return to the list

## Requirements

* Wi-Fi: scanning an entry fetches it from https://pokeapi.co and the PokeAPI
  sprite repository. Put the network name and password in `secrets.py`
  (`WIFI_SSID` and `WIFI_PASSWORD`), for example through the Settings app.
* Storage: scanned entries are cached under `/state/pokedex`. The newest 80
  are kept; older ones are dropped automatically.

The Pokemon names list in `assets/names.txt` was generated from PokeAPI's
species data so the list works before anything has been scanned.
