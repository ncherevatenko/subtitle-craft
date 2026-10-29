"""Synthetic regression tests; no downloaded media or subtitle corpus required."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import argparse
import importlib.util
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'subtitle_audit.py'
SPEC = importlib.util.spec_from_file_location('subtitle_audit_tested', SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class SubtitleAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='subtitle-audit-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def srt(self, name, cues):
        path = self.root / name
        path.write_text('\n'.join(
            f'{index}\n{start} --> {end}\n{text}\n'
            for index, start, end, text in cues
        ), encoding='utf-8')
        return path

    def validate(self, path, expected=None, strict=False):
        options = argparse.Namespace(
            srt=str(path), expected_cues=expected, strict_overlaps=strict,
            max_lines=2, max_chars=42,
        )
        output = StringIO()
        with redirect_stdout(output):
            code = audit.validate(options)
        return code, output.getvalue()

    def align(self, source, target):
        options = argparse.Namespace(
            source=str(source), target=str(target), tolerance_ms=250,
            all=True, output=None,
        )
        output = StringIO()
        with redirect_stdout(output):
            code = audit.audit(options)
        self.assertEqual(code, 0)
        return output.getvalue()

    def test_parse_preserves_original_timing_and_lines(self):
        path = self.srt('target.srt', [
            (1, '00:01:02,030', '00:01:04,050', 'Первая строка\nВторая строка'),
        ])
        cue, = audit.parse_srt(path)
        self.assertEqual(cue.start_ms, 62030)
        self.assertEqual(cue.end_ms, 64050)
        self.assertEqual(cue.lines, ('Первая строка', 'Вторая строка'))

    def test_bom_and_crlf_are_supported(self):
        path = self.root / 'bom.srt'
        path.write_bytes(
            '\ufeff1\r\n00:00:01,000 --> 00:00:02,000\r\nText\r\n'
            .encode('utf-8')
        )
        self.assertEqual(audit.parse_srt(path)[0].lines, ('Text',))

    def test_alignment_uses_times_not_indices(self):
        source = self.srt('source.srt', [
            (7, '00:00:01,000', '00:00:02,000', 'Four boats.'),
        ])
        target = self.srt('target.srt', [
            (1, '00:00:00,000', '00:00:00,500', 'Надпись'),
            (2, '00:00:01,000', '00:00:02,000', 'Четыре лодки.'),
        ])
        result = self.align(source, target)
        self.assertIn('EN[7]', result)
        self.assertIn('[2] Четыре лодки.', result)
        self.assertIn('missing=0', result)

    def test_missing_spoken_target_is_flagged(self):
        source = self.srt('source.srt', [
            (1, '00:00:10,000', '00:00:11,000', 'Turn back.'),
        ])
        target = self.srt('target.srt', [])
        self.assertIn('MISSING_TARGET', self.align(source, target))

    def test_target_only_screen_text_is_not_missing_dialogue(self):
        source = self.srt('source.srt', [
            (1, '00:00:02,000', '00:00:03,000', 'A message.'),
        ])
        target = self.srt('target.srt', [
            (1, '00:00:00,000', '00:00:01,000', 'НОВОЕ СООБЩЕНИЕ'),
            (2, '00:00:02,000', '00:00:03,000', 'Сообщение.'),
        ])
        self.assertIn('source_dialogue=1 missing=0', self.align(source, target))
        self.assertEqual(len(audit.parse_srt(target)), 2)

    def test_music_and_sound_markers_are_not_dialogue(self):
        path = self.srt('markers.srt', [
            (1, '00:00:00,000', '00:00:01,000', '♪ music ♪'),
            (2, '00:00:01,000', '00:00:02,000', '[door closes]'),
            (3, '00:00:02,000', '00:00:03,000', '<i>Hello.</i>'),
        ])
        self.assertEqual([audit.is_dialogue(c) for c in audit.parse_srt(path)],
                         [False, False, True])

    def test_numeric_difference_is_only_a_review_prompt(self):
        source = self.srt('source.srt', [
            (1, '00:00:00,000', '00:00:01,000', '12 boats.'),
        ])
        target = self.srt('target.srt', [
            (1, '00:00:00,000', '00:00:01,000', 'Двенадцать лодок.'),
        ])
        self.assertIn('NUMERIC 12', self.align(source, target))
        self.assertEqual(audit.numbers('30,000'), {'30000'})
        # Spaced thousands need manual disposition in the current helper.
        self.assertEqual(audit.numbers('30 000'), {'30', '000'})

    def test_register_loss_is_flagged_without_rewriting(self):
        source = self.srt('source.srt', [
            (1, '00:00:00,000', '00:00:01,000', 'Shit!'),
        ])
        target = self.srt('target.srt', [
            (1, '00:00:00,000', '00:00:01,000', 'Ой!'),
        ])
        before = target.read_bytes()
        self.assertIn('REGISTER', self.align(source, target))
        self.assertEqual(target.read_bytes(), before)

    def test_forced_overlap_is_warning_unless_strict(self):
        path = self.srt('overlap.srt', [
            (1, '00:00:01,000', '00:00:03,000', 'Экранная надпись'),
            (2, '00:00:02,000', '00:00:04,000', 'Реплика'),
        ])
        code, output = self.validate(path, expected=2)
        self.assertEqual(code, 0)
        self.assertIn('errors=0 warnings=1', output)
        code, output = self.validate(path, expected=2, strict=True)
        self.assertEqual(code, 1)
        self.assertIn('errors=1 warnings=0', output)

    def test_count_and_numbering_errors_are_reported(self):
        path = self.srt('bad-index.srt', [
            (2, '00:00:00,000', '00:00:01,000', 'Text'),
        ])
        code, output = self.validate(path, expected=2)
        self.assertEqual(code, 1)
        self.assertIn('index is 2, expected 1', output)
        self.assertIn('cue count is 1, expected 2', output)

    def test_bad_clock_and_reversed_span_are_rejected(self):
        bad_clock = self.srt('bad-clock.srt', [
            (1, '00:60:00,000', '01:00:01,000', 'Text'),
        ])
        with self.assertRaises(audit.SrtParseError):
            audit.parse_srt(bad_clock)
        reversed_span = self.srt('reversed.srt', [
            (1, '00:00:02,000', '00:00:01,000', 'Text'),
        ])
        self.assertEqual(self.validate(reversed_span)[0], 1)

    def test_validation_checks_visible_text_and_keeps_input_bytes(self):
        path = self.srt('visible.srt', [
            (1, '00:00:00,000', '00:00:01,000', '<i>Valid text</i>'),
        ])
        before = path.read_bytes()
        self.assertEqual(self.validate(path, expected=1)[0], 0)
        self.assertEqual(path.read_bytes(), before)
        empty = self.srt('empty.srt', [
            (1, '00:00:00,000', '00:00:01,000', '<i></i>'),
        ])
        self.assertIn('empty visible text', self.validate(empty)[1])
        too_long = self.srt('long.srt', [
            (1, '00:00:00,000', '00:00:01,000', 'x' * 43),
        ])
        self.assertIn('43 visible characters', self.validate(too_long)[1])


if __name__ == '__main__':
    unittest.main()
