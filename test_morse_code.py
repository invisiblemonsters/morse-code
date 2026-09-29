"""Tests for morse-code."""

import os
import random
import subprocess
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from morse_code import MORSE_TABLE, decode, encode, render_wav, segments

SCRIPT = Path(__file__).resolve().with_name("morse_code.py")


def run_cli(args, stdin_text=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


class EncodeTests(unittest.TestCase):
    def test_known_vectors(self):
        cases = {
            "SOS": "... --- ...",
            "HELLO WORLD": ".... . .-.. .-.. --- / .-- --- .-. .-.. -..",
            "E": ".",
            "T": "-",
            "0": "-----",
            "9": "----.",
            "A B C": ".- / -... / -.-.",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(encode(text), expected)

    def test_case_insensitive(self):
        self.assertEqual(encode("sos"), encode("SOS"))

    def test_whitespace_collapses_to_word_breaks(self):
        self.assertEqual(encode("A   B\nC\tD"), ".- / -... / -.-. / -..")

    def test_every_table_character_encodes_to_its_code(self):
        for char, code in MORSE_TABLE.items():
            with self.subTest(char=char):
                self.assertEqual(encode(char), code)

    def test_rejects_unsupported_characters(self):
        for bad in ("SOS #", "caf\u00e9", "hi \U0001f600"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as ctx:
                    encode(bad)
                self.assertIn("unsupported character", str(ctx.exception))

    def test_error_message_is_ascii_safe(self):
        with self.assertRaises(ValueError) as ctx:
            encode("\u20ac")
        message = str(ctx.exception)
        self.assertIn("\\u20ac", message)
        message.encode("ascii")  # must not raise


class DecodeTests(unittest.TestCase):
    def test_known_vectors(self):
        cases = {
            "... --- ...": "SOS",
            ".... . .-.. .-.. --- / .-- --- .-. .-.. -..": "HELLO WORLD",
            ".---- ..--- ...--": "123",
        }
        for morse, expected in cases.items():
            with self.subTest(morse=morse):
                self.assertEqual(decode(morse), expected)

    def test_round_trip_every_character(self):
        for char in MORSE_TABLE:
            with self.subTest(char=char):
                self.assertEqual(decode(encode(char)), char)

    def test_round_trip_full_character_table(self):
        text = "".join(MORSE_TABLE)
        self.assertEqual(decode(encode(text)), text)

    def test_round_trip_sentences(self):
        sentences = [
            "SOS",
            "HELLO WORLD",
            "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 0123456789",
            "WHAT? OK! GOOD.",
            "CRYPTO: BUY LOW, SELL HIGH.",
            'QUOTED "TEXT" @ HOME',
            "5 DOLLARS + TAX = 6",
            "(PARENS) & MORE; PLUS = MINUS - UNDER_SCORE",
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                self.assertEqual(decode(encode(sentence)), sentence)

    def test_seeded_corpus_round_trip(self):
        rng = random.Random(1337)
        alphabet = "".join(MORSE_TABLE)
        for _ in range(200):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40)))
            self.assertEqual(decode(encode(text)), text)

    def test_whitespace_is_tolerated(self):
        self.assertEqual(decode("   ...    ---    ...   "), "SOS")
        self.assertEqual(decode("... --- ...\n"), "SOS")

    def test_word_separator_styles(self):
        self.assertEqual(decode("... / ---"), "S O")
        self.assertEqual(decode(".../---"), "S O")
        self.assertEqual(decode(".- / -..."), "A B")

    def test_empty_input_decodes_to_empty(self):
        self.assertEqual(decode(""), "")
        self.assertEqual(decode("   "), "")

    def test_rejects_unknown_tokens(self):
        for bad in ("......", "... x ...", ".....-"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    decode(bad)


class SegmentTests(unittest.TestCase):
    def test_sos_segment_layout(self):
        segs = segments("... --- ...")
        marks = [units for kind, units in segs if kind == "mark"]
        silences = [units for kind, units in segs if kind == "silence"]
        self.assertEqual(marks, [1, 1, 1, 3, 3, 3, 1, 1, 1])
        self.assertEqual(silences, [1, 1, 3, 1, 1, 3, 1, 1])
        self.assertEqual(sum(units for _, units in segs), 27)

    def test_word_gap_replaces_letter_gap(self):
        segs = segments(".- / -...")
        silences = [units for kind, units in segs if kind == "silence"]
        self.assertEqual(silences, [1, 7, 1, 1, 1])
        self.assertEqual(sum(units for _, units in segs), 21)

    def test_single_dash(self):
        self.assertEqual(segments("-"), [("mark", 3.0)])

    def test_leading_separator_only(self):
        self.assertEqual(segments("/"), [("silence", 7.0)])

    def test_empty_input(self):
        self.assertEqual(segments(""), [])

    def test_invalid_symbols_rejected(self):
        for bad in ("..x..", ".- / z"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    segments(bad)


class WavTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def path(self, name):
        return os.path.join(self.tmp, name)

    def read_wav(self, path):
        with wave.open(path, "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            return (
                wav_file.getnchannels(),
                wav_file.getsampwidth(),
                wav_file.getframerate(),
                wav_file.getnframes(),
                array("h", frames),
            )

    def test_structure_and_exact_length(self):
        path = self.path("sos.wav")
        duration = render_wav("... --- ...", path)
        channels, width, rate, frames, samples = self.read_wav(path)
        self.assertEqual((channels, width, rate), (1, 2, 8000))
        expected_frames = 27 * round(0.060 * 8000)
        self.assertEqual(frames, expected_frames)
        self.assertEqual(len(samples), expected_frames)
        self.assertAlmostEqual(duration, expected_frames / 8000, places=6)

    def test_tone_and_silence_placement(self):
        path = self.path("sos.wav")
        render_wav("... --- ...", path)
        _, _, _, _, samples = self.read_wav(path)
        dot_n = round(0.060 * 8000)
        first_dot = samples[:dot_n]
        gap = samples[dot_n:2 * dot_n]
        self.assertEqual(samples[0], 0)  # envelope starts at zero
        self.assertEqual(samples[-1], 0)  # envelope ends at zero
        self.assertGreater(max(abs(value) for value in first_dot), 15000)
        self.assertEqual(max(abs(value) for value in gap), 0)  # gap between dots is silent
        self.assertLessEqual(max(abs(value) for value in samples), 16384)

    def test_deterministic_output(self):
        first, second = self.path("a.wav"), self.path("b.wav")
        render_wav("... --- ...", first)
        render_wav("... --- ...", second)
        self.assertEqual(Path(first).read_bytes(), Path(second).read_bytes())

    def test_duration_scales_with_speed(self):
        message = "... --- ..."
        total_units = sum(units for _, units in segments(message))
        for wpm in (5, 12.5, 20, 25, 60):
            with self.subTest(wpm=wpm):
                path = self.path(f"speed_{wpm}.wav")
                duration = render_wav(message, path, wpm=wpm)
                expected = total_units * (1200.0 / wpm) / 1000.0
                self.assertAlmostEqual(duration, expected, delta=0.002)
                _, _, _, frames, _ = self.read_wav(path)
                self.assertAlmostEqual(frames / 8000, expected, delta=0.002)

    def test_validation_errors(self):
        path = self.path("x.wav")
        with self.assertRaises(ValueError):
            render_wav("...", path, wpm=0)
        with self.assertRaises(ValueError):
            render_wav("...", path, wpm=-10)
        with self.assertRaises(ValueError):
            render_wav("...", path, freq=0)
        with self.assertRaises(ValueError):
            render_wav("...", path, freq=5000, sample_rate=8000)
        with self.assertRaises(ValueError):
            render_wav("...", path, amplitude=0)
        with self.assertRaises(ValueError):
            render_wav("...", path, amplitude=2)
        with self.assertRaises(ValueError):
            render_wav("..x..", path)
        self.assertFalse(os.path.exists(path))  # no partial file on errors


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def test_encode(self):
        result = run_cli(["encode", "SOS"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "... --- ...")

    def test_decode(self):
        result = run_cli(["decode", "... --- ... / .-.. --- .--"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "SOS LOW")

    def test_stdin_when_argument_omitted(self):
        result = run_cli(["encode"], stdin_text="sos\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "... --- ...")

    def test_dash_reads_stdin(self):
        result = run_cli(["decode", "-"], stdin_text="... --- ...\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "SOS")

    def test_encode_error_exit_code(self):
        result = run_cli(["encode", "SOS#"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", result.stderr.lower())

    def test_decode_error_exit_code(self):
        result = run_cli(["decode", ".....-"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", result.stderr.lower())

    def test_empty_input_is_an_error(self):
        result = run_cli(["encode"], stdin_text="   \n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("empty input", result.stderr)

    def test_wav_flag(self):
        path = os.path.join(self.tmp, "out.wav")
        result = run_cli(["encode", "SOS", "--wav", path, "--wpm", "10"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "... --- ...")
        self.assertIn("wrote", result.stderr)
        with wave.open(path, "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 8000)
            self.assertEqual(wav_file.getnframes(), 27 * round(0.12 * 8000))

    def test_version(self):
        result = run_cli(["--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("1.0.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
