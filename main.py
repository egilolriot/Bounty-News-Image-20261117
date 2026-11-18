#!/usr/bin/env python3
"""
news-image-20261117 -- "Sum up 17 November's world news in one image"

A fully deterministic, standard-library-only Python program that renders a
1024x1024 newspaper-front-page / infographic PNG and writes it to
$MAKEFUN_OUTPUT_DIR/entry.png (default /output/entry.png).

Determinism: no wall clock, no randomness, no timestamps anywhere in the
output. The PNG encoder writes only IHDR / IDAT / IEND chunks (no tIME,
iTXt or any other ancillary chunk), and zlib compression at a fixed level
is byte-for-byte reproducible, so two runs produce identical bytes.

Structure:
  * STORIES            -- data: list of dicts (category, headline, subline,
                        icon, accent). Placeholder stories for now; the
                        coordinator replaces them with researched stories.
  * FONT               -- hand-written 5x7 bitmap font (A-Z, 0-9, punctuation).
  * Canvas             -- pixel buffer + drawing primitives (rect, line,
                        circle, text with wrapping / alignment).
  * PNG encoder        -- hand-written, zlib only (IHDR, IDAT, IEND).
  * Icons              -- small vector-style icons drawn from primitives.
  * Layout             -- masthead + lead story + 2x2 grid + bottom story
                        + footer, all from STORIES.
"""

import os
import struct
import zlib

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

WIDTH = 1024
HEIGHT = 1024

# Palette
PAPER = (250, 247, 240)      # warm newsprint off-white
CARD = (255, 255, 255)       # story card white
INK = (24, 30, 38)           # near-black headline ink
MUTED = (96, 104, 116)       # grey subline text
NAVY = (16, 39, 63)          # masthead band
GOLD = (217, 164, 65)        # masthead rule / accents
RULE = (216, 210, 196)       # hairline rules
WHITE = (255, 255, 255)
TAG_TEXT = (255, 255, 255)

DATE_LINE = "TUESDAY, 17 NOVEMBER 2026"
MASTHEAD_TITLE = "THE WORLD IN ONE PAGE"
FOOTER_LINE = "SIX STORIES FROM AROUND THE WORLD - SUMMARISED IN A SINGLE IMAGE"

# --------------------------------------------------------------------------
# STORIES -- researched real stories for Tuesday 17 November 2026.
# Each headline/subline was verified against 2+ independent sources
# (Reuters, AP, BBC, PAHO/WHO, UN News). All are events that happened,
# or were first reported, on 17 Nov 2026. Headlines 28-35 chars, sublines
# 48-54 chars. Mongolia resignation (verified) is held as a backup;
# the six below give the broadest spread across regions and fields.
# --------------------------------------------------------------------------

STORIES = [
    {
        "category": "CONFLICT",
        "headline": "US STRIKES IRAN AFTER DRONE ATTACK",
        "subline": "US jets hit Qeshm site after Iran drones hit Bahrain",
        "icon": "rocket",
        "accent": (122, 32, 48),     # crimson
    },
    {
        "category": "CONFLICT",
        "headline": "KERCH BRIDGE ROAD SPAN COLLAPSES",
        "subline": "Ukraine strike drops road arch into Kerch Strait",
        "icon": "globe",
        "accent": (18, 90, 66),      # deep green
    },
    {
        "category": "MARKETS",
        "headline": "NVIDIA REVENUE DOUBLES TO $115.8BN",
        "subline": "First results since Huang exit; board says no return",
        "icon": "chart",
        "accent": (26, 82, 150),     # blue
    },
    {
        "category": "POLITICS",
        "headline": "TRUMP LANDS IN MANILA FOR ASIA TALKS",
        "subline": "Quad talks first, then Xi and Putin in Shenzhen",
        "icon": "flag",
        "accent": (58, 48, 110),     # indigo
    },
    {
        "category": "HEALTH",
        "headline": "US LOSES MEASLES-FREE STATUS",
        "subline": "PAHO ends 26-year status after 5,412 cases in 2026",
        "icon": "cross",
        "accent": (20, 110, 118),    # teal
    },
    {
        "category": "HEALTH",
        "headline": "EBOLA CASES DOUBLE IN DR CONGO",
        "subline": "WHO: over 11,000 cases, 5,400 deaths in 8 provinces",
        "icon": "cross",
        "accent": (160, 82, 30),     # burnt orange
    },
]

# --------------------------------------------------------------------------
# Hand-written 5x7 bitmap font.
# Each glyph is 7 rows of 5 characters; '#' is a set pixel, '.' is empty.
# Covers A-Z, 0-9, space and . , : ; ' " - ( ) / % $ & ! ? + =
# All text is upper-cased before rendering (newspaper style), so the
# uppercase glyph set is sufficient for every string in this program.
# --------------------------------------------------------------------------

FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ";": ("00000", "01100", "01100", "00000", "01100", "00100", "01000"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    '"': ("01010", "01010", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "$": ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    "&": ("01100", "10010", "10100", "01000", "10101", "10010", "01101"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00110", "00100", "00000", "00100"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
}

# Unknown characters fall back to a visible "?" box so nothing is ever
# silently skipped or garbled.
_FALLBACK = ("11111", "10001", "10001", "10001", "10001", "10001", "11111")

GLYPH_W = 5
GLYPH_H = 7
ADVANCE = 6  # glyph width + 1 column of inter-glyph spacing, in font units


def text_width(text, scale):
    """Pixel width of `text` rendered at integer `scale` (no trailing gap)."""
    text = text.upper()
    if not text:
        return 0
    return len(text) * ADVANCE * scale - scale


def _fit_line(line, scale, max_width):
    """Truncate `line` with '...' so it fits in max_width at scale."""
    if text_width(line, scale) <= max_width:
        return line
    ellipsis = "..."
    while line and text_width(line + ellipsis, scale) > max_width:
        line = line[:-1]
    return line + ellipsis if line else ellipsis


def wrap_text(text, scale, max_width, max_lines):
    """Greedy word wrap of `text` (upper-cased) into at most `max_lines`
    lines, each fitting `max_width` px at `scale`. Over-long last lines are
    truncated with '...'. Never returns more than max_lines lines."""
    text = text.upper()
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        if text_width(trial, scale) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            # A single word wider than the box: hard-truncate it.
            current = _fit_line(word, scale, max_width)
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        # Merge everything from the last allowed line onward, then
        # truncate that merged line with '...' so nothing is dropped
        # silently and no line ever exceeds max_width.
        tail = " ".join(lines[max_lines - 1:])
        lines = lines[:max_lines - 1]
        lines.append(_fit_line(tail, scale, max_width))
    return lines


# --------------------------------------------------------------------------
# Canvas: RGB pixel buffer + drawing primitives
# --------------------------------------------------------------------------

class Canvas:
    def __init__(self, width, height, bg):
        self.w = width
        self.h = height
        # Flat RGB bytearray; row-major.
        self.px = bytearray(bg) * (width * height)

    def _idx(self, x, y):
        return (y * self.w + x) * 3

    def set_pixel(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = self._idx(x, y)
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]

    def fill_rect(self, x, y, w, h, color):
        """Filled rectangle, clipped to the canvas."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = self._idx(x0, yy)
            self.px[i:i + len(row)] = row

    def hline(self, x, y, w, color):
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.fill_rect(x, y, 1, h, color)

    def rect_border(self, x, y, w, h, color, t=1):
        self.fill_rect(x, y, w, t, color)
        self.fill_rect(x, y + h - t, w, t, color)
        self.fill_rect(x, y, t, h, color)
        self.fill_rect(x + w - t, y, t, h, color)

    def line(self, x0, y0, x1, y1, color, thick=1):
        """Bresenham line with square thickness."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = thick // 2
        while True:
            self.fill_rect(x0 - half, y0 - half, thick, thick, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_circle(self, cx, cy, r, color):
        """Filled circle via horizontal scanlines."""
        r2 = r * r
        for dy in range(-r, r + 1):
            dx = int((r2 - dy * dy) ** 0.5)
            self.fill_rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)

    def circle_outline(self, cx, cy, r, color, thick=1):
        """Circle outline (midpoint algorithm), square thickness."""
        x = 0
        y = r
        d = 1 - r
        half = thick // 2
        while x <= y:
            for px, py in ((cx + x, cy + y), (cx - x, cy + y),
                           (cx + x, cy - y), (cx - x, cy - y),
                           (cx + y, cy + x), (cx - y, cy + x),
                           (cx + y, cy - x), (cx - y, cy - x)):
                self.fill_rect(px - half, py - half, thick, thick, color)
            x += 1
            if d < 0:
                d += 2 * x + 1
            else:
                y -= 1
                d += 2 * (x - y) + 1

    # -- text ---------------------------------------------------------------

    def draw_char(self, x, y, ch, scale, color):
        glyph = FONT.get(ch, _FALLBACK)
        for row in range(GLYPH_H):
            bits = glyph[row]
            for col in range(GLYPH_W):
                if bits[col] == "1":
                    self.fill_rect(x + col * scale, y + row * scale,
                                   scale, scale, color)

    def draw_text(self, x, y, text, scale, color, align="left"):
        """Draw one line of text. align: 'left' | 'center' | 'right'
        relative to x. Returns the pixel width drawn."""
        text = text.upper()
        w = text_width(text, scale)
        if align == "center":
            x -= w // 2
        elif align == "right":
            x -= w
        cx = x
        for ch in text:
            self.draw_char(cx, y, ch, scale, color)
            cx += ADVANCE * scale
        return w

    def draw_text_block(self, x, y, lines, scale, color, line_gap=0):
        """Draw pre-wrapped lines; line height = 7*scale + line_gap."""
        for i, line in enumerate(lines):
            self.draw_text(x, y + i * (GLYPH_H * scale + line_gap),
                           line, scale, color)

    def draw_tag(self, x, y, text, scale, bg, fg=TAG_TEXT):
        """Category tag: filled pill with centred text."""
        text = text.upper()
        pad_x = 4 * scale
        w = text_width(text, scale) + 2 * pad_x
        h = GLYPH_H * scale + 2 * scale
        self.fill_rect(x, y, w, h, bg)
        self.draw_text(x + pad_x, y + scale, text, scale, fg)
        return w


# --------------------------------------------------------------------------
# Icons -- small, clean pictograms drawn from primitives inside a tile.
# Each takes the tile's top-left corner, its size, and the ink colour.
# --------------------------------------------------------------------------

def draw_icon(canvas, name, x, y, size, ink):
    """Draw icon `name` inside the square (x, y, size, size)."""
    u = max(2, size // 16)          # unit: icon grid step
    cx = x + size // 2
    cy = y + size // 2

    if name == "globe":
        r = size // 2 - 2 * u
        canvas.fill_circle(cx, cy, r, ink)
        # latitude / longitude lines in the tile colour are faked by
        # drawing thin arcs of the background: use PAPER-white gaps.
        canvas.circle_outline(cx, cy, r, ink, 1)
        canvas.fill_rect(cx - u // 2, cy - r, u, 2 * r, PAPER)
        canvas.fill_rect(cx - r, cy - u // 2, 2 * r, u, PAPER)
        canvas.fill_rect(cx - r, cy - r // 2, 2 * r, u, PAPER)
        canvas.fill_rect(cx - r, cy + r // 2, 2 * r, u, PAPER)

    elif name == "chart":
        # axes
        canvas.fill_rect(x + 3 * u, y + size - 4 * u, size - 6 * u, u, ink)
        canvas.fill_rect(x + 3 * u, y + 3 * u, u, size - 6 * u, ink)
        # rising bars
        canvas.fill_rect(x + 4 * u, y + size - 8 * u, 2 * u, 4 * u, ink)
        canvas.fill_rect(x + 7 * u, y + size - 10 * u, 2 * u, 6 * u, ink)
        canvas.fill_rect(x + 10 * u, y + size - 12 * u, 2 * u, 8 * u, ink)
        # arrow
        canvas.line(x + 4 * u, y + size - 8 * u, x + 13 * u, y + 4 * u,
                    ink, u)
        canvas.line(x + 13 * u, y + 4 * u, x + 10 * u, y + 4 * u, ink, u)
        canvas.line(x + 13 * u, y + 4 * u, x + 13 * u, y + 7 * u, ink, u)

    elif name == "ballot":
        bx, by = x + 3 * u, y + 5 * u
        bw, bh = size - 6 * u, size - 8 * u
        canvas.rect_border(bx, by, bw, bh, ink, u)
        canvas.fill_rect(bx + 2 * u, by + u, bw - 4 * u, u, ink)  # slot
        # check mark above the box
        canvas.line(bx + 2 * u, by - 2 * u, bx + 4 * u, by, ink, u)
        canvas.line(bx + 4 * u, by, bx + 8 * u, by - 4 * u, ink, u)

    elif name == "trophy":
        # cup
        canvas.fill_rect(cx - 4 * u, y + 3 * u, 8 * u, 6 * u, ink)
        canvas.fill_rect(cx - 5 * u, y + 2 * u, 10 * u, 2 * u, ink)
        # handles
        canvas.fill_rect(cx - 6 * u, y + 4 * u, u, 3 * u, ink)
        canvas.fill_rect(cx + 5 * u, y + 4 * u, u, 3 * u, ink)
        # stem + base
        canvas.fill_rect(cx - u, y + 9 * u, 2 * u, 3 * u, ink)
        canvas.fill_rect(cx - 4 * u, y + 12 * u, 8 * u, 2 * u, ink)

    elif name == "rocket":
        # body
        canvas.fill_rect(cx - 2 * u, y + 4 * u, 4 * u, 7 * u, ink)
        # nose cone (triangle)
        for i in range(4):
            wdt = 4 * u - i * u
            canvas.fill_rect(cx - wdt // 2, y + i * u, wdt, u, ink)
        # window
        canvas.fill_circle(cx, cy - u, u, PAPER)
        # fins
        canvas.fill_rect(cx - 4 * u, y + 9 * u, 2 * u, 3 * u, ink)
        canvas.fill_rect(cx + 2 * u, y + 9 * u, 2 * u, 3 * u, ink)
        # flame
        canvas.fill_rect(cx - u, y + 11 * u, 2 * u, 2 * u, GOLD)
        canvas.fill_rect(cx - u // 2, y + 13 * u, u, 2 * u, GOLD)

    elif name == "flag":
        # pole
        canvas.fill_rect(x + 3 * u, y + 2 * u, u, size - 4 * u, ink)
        # flag: two horizontal stripes
        fw, fh = size - 6 * u, size // 2 - 2 * u
        canvas.fill_rect(x + 4 * u, y + 2 * u, fw, fh // 2, ink)
        canvas.fill_rect(x + 4 * u, y + 2 * u + fh // 2, fw, fh // 2, GOLD)

    elif name == "cross":
        # medical plus sign (health stories)
        canvas.fill_rect(cx - 2 * u, y + 3 * u, 4 * u, 10 * u, ink)
        canvas.fill_rect(cx - 5 * u, y + 6 * u, 10 * u, 4 * u, ink)

    else:  # fallback: simple star/dot
        canvas.fill_circle(cx, cy, size // 4, ink)


# --------------------------------------------------------------------------
# PNG encoder -- hand-written, stdlib only (zlib + struct).
# Writes IHDR, IDAT, IEND only. No ancillary chunks, no timestamps.
# --------------------------------------------------------------------------

def _chunk(chunk_type, data):
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc)
    return (struct.pack(">I", len(data)) + chunk_type + data
            + struct.pack(">I", crc & 0xFFFFFFFF))


def encode_png(canvas):
    """Encode a Canvas as a valid 1024x1024 RGB PNG (colour type 2)."""
    w, h = canvas.w, canvas.h
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    # Raw scanlines: filter byte 0 (None) + RGB bytes per row.
    raw = bytearray((w * 3 + 1) * h)
    row_len = w * 3
    for yy in range(h):
        raw[yy * (row_len + 1)] = 0
        start = yy * (row_len + 1) + 1
        raw[start:start + row_len] = canvas.px[yy * row_len:(yy + 1) * row_len]
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    return png


# --------------------------------------------------------------------------
# Layout -- newspaper front page, 1024x1024.
# --------------------------------------------------------------------------

MARGIN = 40
CONTENT_W = WIDTH - 2 * MARGIN  # 944


def render(stories):
    cv = Canvas(WIDTH, HEIGHT, PAPER)

    # ---- Masthead band ---------------------------------------------------
    BAND_H = 168
    cv.fill_rect(0, 0, WIDTH, BAND_H, NAVY)
    cv.draw_text(WIDTH // 2, 26, MASTHEAD_TITLE, 3, GOLD, align="center")
    # Date: the largest type on the page.
    cv.draw_text(WIDTH // 2, 76, DATE_LINE, 5, WHITE, align="center")
    cv.draw_text(WIDTH // 2, 132, "CONFLICT  -  MARKETS  -  POLITICS  -  HEALTH",
                 2, (150, 168, 188), align="center")
    cv.fill_rect(0, BAND_H, WIDTH, 4, GOLD)

    y = BAND_H + 24  # 192

    # ---- Lead story (full width) -----------------------------------------
    lead = stories[0]
    lead_h = 208
    cv.fill_rect(MARGIN, y, CONTENT_W, lead_h, CARD)
    cv.rect_border(MARGIN, y, CONTENT_W, lead_h, RULE, 1)
    cv.fill_rect(MARGIN, y, 8, lead_h, lead["accent"])  # accent spine
    icon_size = 140
    ix, iy = MARGIN + 28, y + (lead_h - icon_size) // 2
    cv.fill_rect(ix, iy, icon_size, icon_size, lead["accent"])
    draw_icon(cv, lead["icon"], ix, iy, icon_size, WHITE)
    tx = ix + icon_size + 24
    tw = MARGIN + CONTENT_W - 24 - tx
    ty = y + 24
    cv.draw_tag(tx, ty, lead["category"] + "  -  LEAD STORY", 2, lead["accent"])
    ty += 14 + 16
    headline_lines = wrap_text(lead["headline"], 4, tw, 2)
    cv.draw_text_block(tx, ty, headline_lines, 4, INK, line_gap=6)
    ty += len(headline_lines) * (GLYPH_H * 4 + 6) + 10
    sub_lines = wrap_text(lead["subline"], 2, tw, 2)
    cv.draw_text_block(tx, ty, sub_lines, 2, MUTED, line_gap=4)
    y += lead_h + 20

    # ---- Grid: stories 2-5 in a 2x2 grid ----------------------------------
    grid = stories[1:5]
    cell_w = (CONTENT_W - 24) // 2  # 460
    cell_h = 172
    for row in range(2):
        for col in range(2):
            s = grid[row * 2 + col]
            cx0 = MARGIN + col * (cell_w + 24)
            cy0 = y + row * (cell_h + 20)
            cv.fill_rect(cx0, cy0, cell_w, cell_h, CARD)
            cv.rect_border(cx0, cy0, cell_w, cell_h, RULE, 1)
            cv.fill_rect(cx0, cy0, cell_w, 5, s["accent"])  # top accent bar
            isize = 84
            ix, iy = cx0 + 18, cy0 + (cell_h - isize) // 2
            cv.fill_rect(ix, iy, isize, isize, s["accent"])
            draw_icon(cv, s["icon"], ix, iy, isize, WHITE)
            tx = ix + isize + 16
            tw = cx0 + cell_w - 16 - tx
            ty = cy0 + 20
            cv.draw_tag(tx, ty, s["category"], 2, s["accent"])
            ty += 14 + 10
            h_lines = wrap_text(s["headline"], 3, tw, 3)
            cv.draw_text_block(tx, ty, h_lines, 3, INK, line_gap=4)
            ty += len(h_lines) * (GLYPH_H * 3 + 4) + 8
            s_lines = wrap_text(s["subline"], 2, tw, 2)
            cv.draw_text_block(tx, ty, s_lines, 2, MUTED, line_gap=4)
    y += 2 * cell_h + 20 + 20

    # ---- Bottom story (full width) ----------------------------------------
    bottom = stories[5]
    bot_h = 116
    cv.fill_rect(MARGIN, y, CONTENT_W, bot_h, CARD)
    cv.rect_border(MARGIN, y, CONTENT_W, bot_h, RULE, 1)
    cv.fill_rect(MARGIN, y, 8, bot_h, bottom["accent"])
    isize = 84
    ix, iy = MARGIN + 28, y + (bot_h - isize) // 2
    cv.fill_rect(ix, iy, isize, isize, bottom["accent"])
    draw_icon(cv, bottom["icon"], ix, iy, isize, WHITE)
    tx = ix + isize + 24
    tw = MARGIN + CONTENT_W - 24 - tx
    ty = y + 20
    cv.draw_tag(tx, ty, bottom["category"], 2, bottom["accent"])
    ty += 14 + 10
    h_lines = wrap_text(bottom["headline"], 3, tw, 1)
    cv.draw_text_block(tx, ty, h_lines, 3, INK, line_gap=4)
    ty += len(h_lines) * (GLYPH_H * 3 + 4) + 8
    s_lines = wrap_text(bottom["subline"], 2, tw, 1)
    cv.draw_text_block(tx, ty, s_lines, 2, MUTED, line_gap=4)
    y += bot_h + 20

    # ---- Footer ------------------------------------------------------------
    cv.hline(MARGIN, y, CONTENT_W, RULE)
    cv.draw_text(WIDTH // 2, y + 14, FOOTER_LINE, 2, MUTED, align="center")

    return cv


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")

    canvas = render(STORIES)
    png = encode_png(canvas)
    if len(png) > 1024 * 1024:
        raise SystemExit("entry.png exceeds 1 MiB: %d bytes" % len(png))
    with open(out_path, "wb") as f:
        f.write(png)
    print("wrote %s (%d bytes, %dx%d)" % (out_path, len(png), WIDTH, HEIGHT))


if __name__ == "__main__":
    main()
