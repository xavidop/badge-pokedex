# Drives the Pokedex app's update() on the badge with simulated buttons.
# Screenshots are run-length encoded and written to /state/shots for copying afterwards.
import sys, os, time, gc, builtins, json
from array import array

DEV = '/state/dev'
captured = []
builtins.run = lambda fn: captured.append(fn)
real_pressed, real_held = badge.pressed, badge.held
held_now = set()
pressed_now = set()


def fake_pressed(button=None):
    return (button in pressed_now) if button is not None else set(pressed_now)


def fake_held(button=None):
    return (button in held_now) if button is not None else set(held_now)


badge.pressed = fake_pressed
badge.held = fake_held

# tidy /state and seed the cache from distilled records copied over USB
for d in ('/state/shots',):
    try: os.mkdir(d)
    except OSError: pass
for n in os.listdir('/state/shots'): os.remove('/state/shots/' + n)
for n in os.listdir('/state'):
    if n.startswith('shot') and n != 'shots':
        os.remove('/state/' + n)
sys.path.insert(0, DEV)
os.chdir(DEV)
try: os.mkdir('/state/pokedex')
except OSError: pass
for n in os.listdir('/state/pokedex'): os.remove('/state/pokedex/' + n)
for n, png in ((1, '/state/t1.png'), (1025, '/state/t1025.png')):
    with open('/state/seed/%d.json' % n) as src, open('/state/pokedex/%d.json' % n, 'w') as dst: dst.write(src.read())
    with open(png, 'rb') as src, open('/state/pokedex/%d.png' % n, 'wb') as dst: dst.write(src.read())
# the saved state from any previous run should not leak into this one
try: os.remove('/state/pokedex.json')
except OSError: pass
print('state free bytes', os.statvfs('/state')[0] * os.statvfs('/state')[3])

src = open(DEV + '/__init__.py').read().replace('APP_DIR = "/system/apps/pokedex"', 'APP_DIR = "%s"' % DEV)
g = {'__name__': 'pokedex_dev'}
t = time.ticks_ms()
exec(src, g)
print('import took', time.ticks_diff(time.ticks_ms(), t), 'ms; cache', g['state']['cache'], 'seen', g['state']['seen'])
update = captured[0]
shots = 0


def rle(raw):
    pixels = array('H', raw)
    out = array('H')
    prev = pixels[0]
    count = 0
    for value in pixels:
        if value == prev and count < 65535:
            count += 1
        else:
            out.append(count)
            out.append(prev)
            prev = value
            count = 1
    out.append(count)
    out.append(prev)
    return out


def step(buttons, capture=False):
    """One frame: a button not down last frame counts as pressed, any down button as held.

    The frame is captured before badge.update(), which flips and clears the buffer.
    """
    global pressed_now, held_now
    buttons = set(buttons)
    pressed_now = buttons - held_now
    held_now = buttons
    t = time.ticks_ms()
    update()
    cost = time.ticks_diff(time.ticks_ms(), t)
    raw = bytes(screen.raw) if capture else None
    badge.update()
    return cost, raw


def frames(n, buttons=(), label=None, shot=False):
    global shots
    worst = 0
    raw = None
    for i in range(n):
        cost, raw = step(buttons if i == 0 else (), capture=shot and i == n - 1)
        worst = max(worst, cost)
    if shot:
        t = time.ticks_ms()
        packed = rle(raw)
        with open('/state/shots/%d.rle' % shots, 'wb') as f:
            f.write(packed)
        print('SHOT %d [%s] worst frame %d ms, mode %d, cursor %d, rle %d bytes in %d ms' % (
            shots, label, worst, g['mode'], g['cursor'], len(packed) * 2, time.ticks_diff(time.ticks_ms(), t)))
        shots += 1
    return worst


def hold(button, ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        step((button,))
    step(())


badge.update()   # start the badge clock before the first frame, as run() would
for label, fn in (('image.load 96x96', lambda: g['load_sprite'](1)), ('State.save', g['save_state']), ('gc.collect', gc.collect), ('load_dex', lambda: g['load_dex'](1)), ('CORE.get', lambda: g['CORE'].get(500))):
    t = time.ticks_ms(); fn(); print('timing', label, time.ticks_diff(time.ticks_ms(), t), 'ms')

frames(3, label='splash', shot=True)
time.sleep_ms(1900)
frames(1, (BUTTON_SELECT,), label='leave splash')
frames(2, label='list', shot=True)
frames(1, (BUTTON_DOWN,)); frames(1, (BUTTON_DOWN,)); frames(1, (BUTTON_DOWN,))
frames(12, label='list cursor 4', shot=True)
hold(BUTTON_DOWN, 2500)
frames(12, label='after holding down 2.5s', shot=True)
frames(1, (BUTTON_UP,)); frames(1, (BUTTON_UP,))
frames(1, (BUTTON_RIGHT,))
frames(12, label='after up up right', shot=True)
g['move_cursor'](-5000)
frames(12, label='cursor at 1', shot=True)
frames(1, (BUTTON_SELECT,))
frames(2, label='entry 1 info', shot=True)
frames(1, (BUTTON_DOWN,)); frames(2, label='entry 1 stats', shot=True)
frames(1, (BUTTON_DOWN,)); frames(2, label='entry 1 dex', shot=True)
frames(1, (BUTTON_RIGHT,))
frames(2, label='entry 2 info scanning (no wifi)', shot=True)
time.sleep_ms(5000)
frames(30, label='entry 2 info after 5s', shot=True)
frames(1, (BUTTON_DOWN,)); frames(2, label='entry 2 stats page while failed', shot=True)
frames(1, (BUTTON_DOWN,)); frames(2, label='entry 2 dex page while failed', shot=True)
frames(1, (BUTTON_BACK,))
frames(12, label='back to list at 2', shot=True)
g['move_cursor'](5000)
frames(12, label='cursor at 1025', shot=True)
frames(1, (BUTTON_SELECT,)); frames(2, label='entry 1025 info', shot=True)
frames(1, (BUTTON_SELECT,)); frames(2, label='entry 1025 shiny toggle (no shiny cached)', shot=True)
frames(1, (BUTTON_DOWN,)); frames(1, (BUTTON_DOWN,)); frames(2, label='entry 1025 dex', shot=True)
frames(1, (BUTTON_MENU,)); frames(2, label='random entry via menu', shot=True)
frames(1, (BUTTON_BACK,))
# a long scroll through the list, watching for frame stalls (garbage collection on the big heap)
stalls = []
for i in range(240):
    before = gc.mem_free()
    cost, _ = step((BUTTON_DOWN,) if i % 2 else ())
    if cost > 60:
        stalls.append((i, cost, before, gc.mem_free()))
print('stalls over 60ms in 240 list frames:', stalls)
frames(2, label='after long scroll', shot=True)
g['on_exit']()
gc.collect(); print('free', gc.mem_free(), 'state', g['state'], 'lights', badge._case_light_values)
badge.pressed, badge.held = real_pressed, real_held
print('DONE', shots)
