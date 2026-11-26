"""Minimal ANSI/VT100 parser for terminal output.

Supports what command output actually uses in practice:

* SGR colours: 16/256/truecolor, bold, dim, italic, underline, inverse, reset
* carriage return (progress bars), backspace, tab stops
* erase-line (``ESC[K`` / ``ESC[1K`` / ``ESC[2K``) and cursor movement
* incomplete escape sequences split across chunks
* OSC / private-mode sequences are swallowed

The parser returns styled *runs* instead of HTML so the Qt view can render
them with ``QTextCharFormat`` without HTML escaping or space collapsing.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace

DEFAULT_FG = "#d7dae1"

ANSI_16 = (
    "#2e3436", "#cc0000", "#4e9a06", "#c4a000",
    "#3465a4", "#75507b", "#06989a", "#d3d7cf",
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
)
ANSI_16_BRIGHT = (
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
    "#888a85", "#ff5f5f", "#b6f56b", "#fff27a",
    "#9fc6f0", "#d3a6cf", "#7df0f0", "#ffffff",
)


@dataclass(frozen=True)
class Style:
    fg: str | None = None
    bg: str | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    inverse: bool = False


DEFAULT_STYLE = Style()
Run = tuple[str, Style]

ZERO_WIDTH = {
    "\u200b",  # zero width space
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\u2060",  # word joiner
    "\ufe0e",  # variation selector-15
    "\ufe0f",  # variation selector-16
}


def char_width(ch: str) -> int:
    """Terminal cell width: 0 (combining/zero-width), 1 (narrow), 2 (wide).

    Uses East Asian Width from unicodedata so CJK/emoji occupy two cells —
    without this, ``\r`` progress bars mis-align on Chinese output.
    """
    if not ch:
        return 0
    if ch in ZERO_WIDTH:
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def text_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def xterm256(index: int) -> str | None:
    if index < 0:
        return None
    if index < 16:
        return ANSI_16[index]
    if index < 232:
        index -= 16
        r = index // 36
        g = (index % 36) // 6
        b = index % 6
        base = (0, 95, 135, 175, 215, 255)
        return f"#{base[r]:02x}{base[g]:02x}{base[b]:02x}"
    if index < 256:
        level = 8 + (index - 232) * 10
        return f"#{level:02x}{level:02x}{level:02x}"
    return None


class AnsiParser:
    def __init__(self, default_style: Style = DEFAULT_STYLE) -> None:
        self.default_style = default_style
        self.reset()

    def reset(self) -> None:
        # each cell is (text, style, is_wide_continuation)
        self._cells: list[tuple[str, Style, bool]] = []
        self._col = 0
        self._style = self.default_style
        self._pending = ""

    # ------------------------------------------------------------------ public
    def feed(self, text: str) -> tuple[list[list[Run]], list[Run] | None]:
        """Consume text; returns (completed_lines, current_partial_runs)."""
        data = self._pending + text
        self._pending = ""
        lines: list[list[Run]] = []
        i = 0
        n = len(data)
        while i < n:
            ch = data[i]
            if ch == "\x1b":
                consumed = self._escape(data, i)
                if consumed is None:  # incomplete sequence
                    self._pending = data[i:]
                    i = n
                    break
                i = consumed
                continue
            if ch == "\r":
                self._col = 0
            elif ch == "\n":
                lines.append(self._render())
                self._cells = []
                self._col = 0
            elif ch == "\b":
                self._col = max(0, self._col - 1)
            elif ch == "\t":
                spaces = 8 - (self._col % 8)
                for _ in range(spaces):
                    self._put(" ")
            elif ch < " ":
                pass
            else:
                self._put(ch)
            i += 1

        partial = self._render() if self._cells else None
        return lines, partial

    def flush(self) -> list[Run] | None:
        runs = self._render() if self._cells else None
        self._cells = []
        self._col = 0
        self._pending = ""
        return runs

    # ----------------------------------------------------------------- internals
    def _put(self, ch: str) -> None:
        width = char_width(ch)
        if width == 0:
            # combining mark: attach to the previous visible cell
            for idx in range(len(self._cells) - 1, -1, -1):
                text, style, cont = self._cells[idx]
                if not cont:
                    self._cells[idx] = (text + ch, style, False)
                    return
            return

        while len(self._cells) < self._col:
            self._cells.append((" ", self.default_style, False))

        if width == 1:
            self._clear_cell(self._col)
            if self._col < len(self._cells):
                self._cells[self._col] = (ch, self._style, False)
            else:
                self._cells.append((ch, self._style, False))
            self._col += 1
            return

        # width == 2: claim two cells, second is a continuation marker
        self._clear_cell(self._col)
        self._clear_cell(self._col + 1)
        while len(self._cells) < self._col + 2:
            self._cells.append((" ", self.default_style, False))
        self._cells[self._col] = (ch, self._style, False)
        self._cells[self._col + 1] = ("", self._style, True)
        self._col += 2

    def _clear_cell(self, index: int) -> None:
        """Blank a cell, and the other half of a wide glyph if overlapped."""
        if index < 0 or index >= len(self._cells):
            return
        text, style, cont = self._cells[index]
        if cont:
            if index > 0:
                self._cells[index - 1] = (" ", self.default_style, False)
            self._cells[index] = (" ", self.default_style, False)
            return
        if index + 1 < len(self._cells) and self._cells[index + 1][2]:
            self._cells[index + 1] = (" ", self.default_style, False)
        self._cells[index] = (" ", self.default_style, False)

    def _render(self) -> list[Run]:
        if not self._cells:
            return []
        runs: list[Run] = []
        buf: list[str] = []
        current = self._cells[0][1]
        for ch, style, cont in self._cells:
            if cont:
                continue  # the wide glyph before it already covers both cells
            if style != current:
                runs.append(("".join(buf), current))
                buf = []
                current = style
            buf.append(ch)
        if buf:
            runs.append(("".join(buf), current))
        return runs

    def _escape(self, data: str, index: int) -> int | None:
        """Handle one escape sequence starting at ``data[index] == ESC``."""
        n = len(data)
        if index + 1 >= n:
            return None
        kind = data[index + 1]
        if kind == "[":
            j = index + 2
            while j < n and not ("\x40" <= data[j] <= "\x7e"):
                j += 1
            if j >= n:
                return None
            final = data[j]
            params = data[index + 2:j]
            if final == "m":
                self._apply_sgr(params)
            elif final == "K":
                self._erase_line(params)
            elif final in "Hf":
                self._col = 0
            elif final == "C":
                self._col += self._first_param(params, 1)
            elif final == "D":
                self._col = max(0, self._col - self._first_param(params, 1))
            elif final == "A":
                pass
            elif final == "B":
                pass
            elif final == "G":
                self._col = max(0, self._first_param(params, 1) - 1)
            return j + 1
        if kind == "]":  # OSC ... BEL or ST
            j = index + 2
            while j < n:
                if data[j] == "\x07":
                    return j + 1
                if data[j] == "\x1b" and j + 1 < n and data[j + 1] == "\\":
                    return j + 2
                j += 1
            return None
        if kind in "()":  # charset designation
            return index + 3 if index + 2 < n else None
        return index + 2  # two-byte sequence

    @staticmethod
    def _first_param(params: str, default: int) -> int:
        if not params:
            return default
        first = params.split(";")[0]
        if first.isdigit():
            return int(first)
        return default

    def _erase_line(self, params: str) -> None:
        mode = self._first_param(params, 0) if params.strip() else 0
        if mode == 1:
            for i in range(min(self._col, len(self._cells))):
                self._clear_cell(i)
        elif mode == 2:
            self._cells = []
            self._col = 0
        else:
            if self._col < len(self._cells) and self._cells[self._col][2]:
                self._clear_cell(self._col)
            del self._cells[self._col:]

    def _apply_sgr(self, params: str) -> None:
        if params == "":
            self._style = self.default_style
            return
        parts = params.split(";")
        i = 0
        style = self._style
        while i < len(parts):
            raw = parts[i]
            code = int(raw) if raw.isdigit() else 0
            if code == 0:
                style = self.default_style
            elif code == 1:
                style = replace(style, bold=True)
            elif code == 2:
                style = replace(style, dim=True)
            elif code == 3:
                style = replace(style, italic=True)
            elif code == 4:
                style = replace(style, underline=True)
            elif code == 7:
                style = replace(style, inverse=True)
            elif code in (21, 22):
                style = replace(style, bold=False, dim=False)
            elif code == 23:
                style = replace(style, italic=False)
            elif code == 24:
                style = replace(style, underline=False)
            elif code == 27:
                style = replace(style, inverse=False)
            elif 30 <= code <= 37:
                style = replace(style, fg=ANSI_16_BRIGHT[code - 30] if style.bold else ANSI_16[code - 30])
            elif code == 39:
                style = replace(style, fg=None)
            elif 40 <= code <= 47:
                style = replace(style, bg=ANSI_16[code - 40])
            elif code == 49:
                style = replace(style, bg=None)
            elif 90 <= code <= 97:
                style = replace(style, fg=ANSI_16_BRIGHT[code - 90])
            elif 100 <= code <= 107:
                style = replace(style, bg=ANSI_16_BRIGHT[code - 100])
            elif code in (38, 48):
                target = "fg" if code == 38 else "bg"
                if i + 1 < len(parts) and parts[i + 1] == "5" and i + 2 < len(parts):
                    colour = xterm256(int(parts[i + 2]) if parts[i + 2].isdigit() else -1)
                    style = replace(style, **{target: colour})
                    i += 2
                elif i + 1 < len(parts) and parts[i + 1] == "2" and i + 4 < len(parts):
                    try:
                        r, g, b = (int(parts[i + 2]), int(parts[i + 3]), int(parts[i + 4]))
                        style = replace(style, **{target: f"#{r:02x}{g:02x}{b:02x}"})
                    except ValueError:
                        pass
                    i += 4
            i += 1
        self._style = style
