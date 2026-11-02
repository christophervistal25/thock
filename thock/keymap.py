"""Linux evdev keycode -> horizontal position (0 = far left, 1 = far right).

Used only to pan sounds; no key identity is kept anywhere.
"""

_ROWS = [
    # (start_x_in_key_units, [(code, width), ...])
    (0.0, [(1, 1), (None, 1), (59, 1), (60, 1), (61, 1), (62, 1), (None, .5), (63, 1), (64, 1), (65, 1), (66, 1),
           (None, .5), (67, 1), (68, 1), (87, 1), (88, 1)]),
    (0.0, [(41, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1), (10, 1), (11, 1), (12, 1), (13, 1), (14, 2)]),
    (0.0, [(15, 1.5), (16, 1), (17, 1), (18, 1), (19, 1), (20, 1), (21, 1), (22, 1), (23, 1), (24, 1), (25, 1), (26, 1), (27, 1), (43, 1.5)]),
    (0.0, [(58, 1.75), (30, 1), (31, 1), (32, 1), (33, 1), (34, 1), (35, 1), (36, 1), (37, 1), (38, 1), (39, 1), (40, 1), (28, 2.25)]),
    (0.0, [(42, 2.25), (44, 1), (45, 1), (46, 1), (47, 1), (48, 1), (49, 1), (50, 1), (51, 1), (52, 1), (53, 1), (54, 2.75)]),
    (0.0, [(29, 1.25), (125, 1.25), (56, 1.25), (57, 6.25), (100, 1.25), (126, 1.25), (127, 1.25), (97, 1.25)]),
]
_NAV = {99: 15.75, 70: 16.75, 119: 17.75, 110: 15.75, 102: 16.75, 104: 17.75, 111: 15.75, 107: 16.75, 109: 17.75,
        103: 16.75, 105: 15.75, 108: 16.75, 106: 17.75}
_PAD = {69: 19, 98: 20, 55: 21, 74: 22, 71: 19, 72: 20, 73: 21, 78: 22, 75: 19, 76: 20, 77: 21, 79: 19, 80: 20,
        81: 21, 96: 22, 82: 19.5, 83: 21}

_MAIN_W = 15.0
POSITIONS = {}
for start, keys in _ROWS:
    x = start
    for code, w in keys:
        if code is not None:
            POSITIONS[code] = (x + w / 2) / _MAIN_W
        x += w
for code, x in _NAV.items():
    POSITIONS[code] = x / 22.5
for code, x in _PAD.items():
    POSITIONS[code] = x / 22.5


def key_x(code):
    """Return pan position for a keycode, scaled so the main block spans most of the stereo field."""
    x = POSITIONS.get(code, 0.5)
    if x <= 1.0 and code not in _NAV and code not in _PAD:
        return 0.06 + x * 0.82          # main block: 0.06 .. 0.88
    return min(1.0, 0.86 + (x - 0.65) * 0.4)


SPACE, ENTER, BACKSPACE = 57, 28, 14
