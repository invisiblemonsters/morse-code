#!/usr/bin/env python3
"""morse-code: translate text to and from Morse code, with optional WAV audio.

Zero dependencies -- Python standard library only.

Conventions
-----------
* Letters within a word are separated by a single space; words are separated
  by ``/`` (an isolated slash token), e.g. ``... --- ... / ... --- ...``.
* Timing follows the ITU standard: one unit = 1200 / WPM milliseconds, a dash
  is three units, and gaps are one unit between elements, three units between
  letters, and seven units between words.
"""

from __future__ import annotations

import argparse
import math
import sys
import wave
from array import array

__all__ = ["MORSE_TABLE", "encode", "decode", "segments", "render_wav", "main"]

__version__ = "1.0.0"

#: ITU Morse code table: character -> code (dots and dashes).
MORSE_TABLE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "$": "...-..-", "@": ".--.-.",
}

_FROM_MORSE = {code: char for char, code in MORSE_TABLE.items()}

DOT_UNITS = 1.0
DASH_UNITS = 3.0
ELEMENT_GAP_UNITS = 1.0
LETTER_GAP_UNITS = 3.0
WORD_GAP_UNITS = 7.0

DEFAULT_WPM = 20.0
DEFAULT_FREQ = 700.0
DEFAULT_SAMPLE_RATE = 8000
DEFAULT_AMPLITUDE = 0.5
DEFAULT_RAMP_MS = 5.0

_UNIT_MS_PER_WPM = 1200.0  # the standard: dot duration in ms = 1200 / WPM


def encode(text: str) -> str:
    """Convert plain text to Morse code.

    Letters are separated by a single space, words by `` / ``. Input is
    case-insensitive. Raises ValueError for characters outside the
    supported set.
    """
    words = []
    for word in text.upper().split():
        codes = []
        for char in word:
            code = MORSE_TABLE.get(char)
            if code is None:
                raise ValueError(f"unsupported character: {char!a}")
            codes.append(code)
        words.append(" ".join(codes))
    return " / ".join(words)


def decode(morse: str) -> str:
    """Convert Morse code back to plain text.

    Extra whitespace is tolerated, and ``/`` marks a word break with or
    without surrounding spaces. Raises ValueError for unknown tokens.
    """
    words = []
    current = []
    for token in morse.replace("/", " / ").split():
        if token == "/":
            words.append("".join(current))
            current = []
            continue
        char = _FROM_MORSE.get(token)
        if char is None:
            raise ValueError(f"unknown Morse token: {token!a}")
        current.append(char)
    words.append("".join(current))
    return " ".join(word for word in words if word)


def segments(morse: str) -> list[tuple[str, float]]:
    """Expand Morse code into ordered audio segments as ``(kind, units)``.

    ``kind`` is ``"mark"`` (tone) or ``"silence"``. Units follow the ITU
    timing standard. Raises ValueError for symbols other than ``.``/``-``.
    """
    result = []
    previous = None  # None at the start, then "letter" or "separator"
    for token in morse.replace("/", " / ").split():
        if token == "/":
            result.append(("silence", WORD_GAP_UNITS))
            previous = "separator"
            continue
        for symbol in token:
            if symbol not in ".-":
                raise ValueError(f"invalid Morse symbol: {symbol!a} in token {token!a}")
        if previous == "letter":
            result.append(("silence", LETTER_GAP_UNITS))
        for index, symbol in enumerate(token):
            result.append(("mark", DOT_UNITS if symbol == "." else DASH_UNITS))
            if index < len(token) - 1:
                result.append(("silence", ELEMENT_GAP_UNITS))
        previous = "letter"
    return result


def render_wav(
    morse: str,
    path: str,
    wpm: float = DEFAULT_WPM,
    freq: float = DEFAULT_FREQ,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = DEFAULT_AMPLITUDE,
    ramp_ms: float = DEFAULT_RAMP_MS,
) -> float:
    """Render Morse code to a mono 16-bit WAV file; return its duration in seconds.

    Timing follows the ITU standard (dot = 1200 / WPM ms). Every tone is
    shaped with a short raised-cosine ramp so the audio has no key clicks.
    """
    if wpm <= 0:
        raise ValueError(f"wpm must be > 0, got {wpm:g}")
    if freq <= 0 or freq >= sample_rate / 2:
        raise ValueError(
            f"freq must be between 0 and {sample_rate / 2:g} Hz (Nyquist), got {freq:g}"
        )
    if not 0 < amplitude <= 1:
        raise ValueError(f"amplitude must be in (0, 1], got {amplitude:g}")

    unit_seconds = _UNIT_MS_PER_WPM / wpm / 1000.0
    ramp_samples = max(1, int(round(ramp_ms * sample_rate / 1000.0)))
    peak = amplitude * 32767.0

    samples = array("h")
    for kind, units in segments(morse):
        count = max(1, int(round(units * unit_seconds * sample_rate)))
        if kind == "silence":
            samples.extend(array("h", bytes(2 * count)))
            continue
        for index in range(count):
            envelope = min(1.0, index / ramp_samples, (count - 1 - index) / ramp_samples)
            tone = math.sin(2.0 * math.pi * freq * index / sample_rate)
            samples.append(int(round(envelope * tone * peak)))

    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.tobytes())
    return len(samples) / sample_rate


def _read_input(value: str | None) -> str:
    if value is None or value == "-":
        value = sys.stdin.read()
    value = value.strip()
    if not value:
        raise ValueError("empty input")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Translate text to and from Morse code, with optional WAV audio.",
        epilog="Reads from stdin when TEXT/MORSE is omitted or '-'.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="convert text to Morse code")
    encode_parser.add_argument(
        "text", nargs="?", default=None,
        help="text to convert; omit or use '-' to read stdin",
    )
    encode_parser.add_argument(
        "--wav", metavar="FILE", help="also render the Morse code to a WAV file",
    )
    encode_parser.add_argument(
        "--wpm", type=float, default=DEFAULT_WPM, metavar="N",
        help=f"audio speed in words per minute (default {DEFAULT_WPM:g})",
    )
    encode_parser.add_argument(
        "--freq", type=float, default=DEFAULT_FREQ, metavar="HZ",
        help=f"audio tone frequency in Hz (default {DEFAULT_FREQ:g})",
    )

    decode_parser = subparsers.add_parser("decode", help="convert Morse code to text")
    decode_parser.add_argument(
        "morse", nargs="?", default=None,
        help="Morse to convert; omit or use '-' to read stdin",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "encode":
            code = encode(_read_input(args.text))
            print(code)
            if args.wav:
                seconds = render_wav(code, args.wav, wpm=args.wpm, freq=args.freq)
                print(
                    f"wrote {args.wav} ({seconds:.2f}s of audio at {args.wpm:g} WPM)",
                    file=sys.stderr,
                )
        else:
            print(decode(_read_input(args.morse)))
    except (ValueError, OSError) as exc:
        print(f"morse: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
