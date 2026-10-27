"""Draw the Pokedex icon: a 16x16 pixel Pokeball scaled to 48x48, paletted PNG."""
import struct, zlib, sys

BALL = [
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
]
PALETTE = {".": (0, 0, 0, 0), "X": (24, 24, 32, 255), "R": (216, 40, 48, 255),
           "L": (248, 120, 120, 255), "W": (240, 240, 232, 255)}
KEYS = list(PALETTE)

def png(path, scale):
    size = 16 * scale
    rows = []
    for line in BALL:
        row = bytes(KEYS.index(c) for c in line for _ in range(scale))
        rows.extend([b"\x00" + row] * scale)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    plte = b"".join(bytes(PALETTE[k][:3]) for k in KEYS)
    trns = bytes(PALETTE[k][3] for k in KEYS)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", plte) + chunk(b"tRNS", trns)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
    open(path, "wb").write(data)
    print(path, size, "x", size, len(data), "bytes")

png(sys.argv[1], 3)
