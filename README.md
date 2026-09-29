# morse-code

A zero-dependency Morse code translator for the command line: encode text to
Morse, decode Morse back to text, and optionally render the result as a WAV
audio file with correct ITU timing. Python standard library only.

```console
$ python morse_code.py encode "SOS"
... --- ...

$ python morse_code.py decode "... --- ... / .-.. --- .--"
SOS LOW

$ python morse_code.py encode "SOS" --wav sos.wav --wpm 25
... --- ...
wrote sos.wav (1.30s of audio at 25 WPM)
```

## Features

- **Encode and decode** — `A`–`Z`, `0`–`9`, and the common punctuation set
  (see below). Encoding is case-insensitive; decoding returns uppercase text.
- **Standard representation** — letters separated by one space, words by
  `/`, e.g. `... --- ... / ... --- ...`.
- **Real audio** — `--wav` renders a mono 16-bit WAV at classic ITU speed
  (dot = 1200 / WPM ms) with a short raised-cosine envelope on every tone, so
  there are no key clicks.
- **Pipe-friendly** — omit the text argument (or pass `-`) to read stdin.

## Usage

```console
python morse_code.py encode "HELLO WORLD"
python morse_code.py decode ".... . .-.. .-.. --- / .-- --- .-. .-.. -.."

# stdin
echo "SOS" | python morse_code.py encode
cat message.morse | python morse_code.py decode

# audio (defaults: 20 WPM, 700 Hz)
python morse_code.py encode "SOS" --wav sos.wav
python morse_code.py encode "SOS" --wav fast.wav --wpm 30 --freq 800
```

### Options

| Command | Option | Description |
| --- | --- | --- |
| `encode` | `TEXT` | Text to convert; omit or use `-` for stdin |
| `encode` | `--wav FILE` | Also render the Morse code to a WAV file |
| `encode` | `--wpm N` | Audio speed in words per minute (default `20`) |
| `encode` | `--freq HZ` | Audio tone frequency in Hz (default `700`) |
| `decode` | `MORSE` | Morse to convert; omit or use `-` for stdin |

### Supported characters

`A`–`Z`, `0`–`9`, and `. , ? ' ! / ( ) & : ; = + - _ " $ @`

Unsupported characters and malformed Morse tokens produce a clear error
message on stderr and exit with code `2`.

## Tests

```console
python -m unittest test_morse_code.py -v
```

The suite covers known encode/decode vectors, round-trips across the entire
character table (plus a seeded 200-document corpus sweep), whitespace and
word-gap handling, error cases, the timing segment model, and the WAV
renderer — structure, exact frame counts, tone/silence placement, envelope
boundaries, determinism, and duration scaling across several speeds.

## License

MIT
