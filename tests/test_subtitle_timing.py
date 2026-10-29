"""Release-timing regression tests; synthetic files only, never controls VLC."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import subtitle_timing as timing
from subtitle_audit import parse_srt


class SubtitleTimingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='subtitle-timing-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.srt('baseline.srt', [
            (1, '00:00:01,000', '00:00:02,000', '<i>СТОЙ!</i>'),
            (2, '00:00:03,000', '00:00:04,000', 'Он не придёт.'),
            (3, '00:00:05,000', '00:00:06,000', 'МЕСТО ВСТРЕЧИ'),
        ])
        self.reference = self.srt('embedded.srt', [
            (1, '00:00:08,800', '00:00:09,800', 'Стой!'),
            (2, '00:00:11,140', '00:00:11,510', 'Он не придёт.'),
            (3, '00:00:12,800', '00:00:13,800', 'Место\nвстречи'),
        ])
        self.prepared = self.srt('prepared.srt', [
            (1, '00:00:01,000', '00:00:02,000', 'Стой!\nПодожди!'),
            (2, '00:00:03,000', '00:00:04,000', 'Он не явится. [?]'),
            (3, '00:00:05,000', '00:00:06,000', 'МЕСТО ВСТРЕЧИ'),
        ])
        self.output = self.root / 'bound.srt'
        self.report = self.root / 'binding.json'

    def srt(self, name, entries):
        path = self.root / name
        path.write_text('\n'.join(
            f'{index}\n{start} --> {end}\n{text}\n'
            for index, start, end, text in entries
        ), encoding='utf-8')
        return path

    def bind(self, **overrides):
        args = dict(baseline=self.baseline, reference=self.reference,
                    prepared=self.prepared, output=self.output, report=self.report)
        args.update(overrides)
        return timing.bind_tracks(**args)

    def test_nonuniform_offsets_use_each_reference_span(self):
        result = self.bind()
        expected = parse_srt(self.reference)
        actual = parse_srt(self.output)
        self.assertEqual([(c.start_ms, c.end_ms) for c in actual],
                         [(c.start_ms, c.end_ms) for c in expected])
        self.assertEqual(result['mapping'][1]['start_delta_ms'], 8140)
        self.assertEqual(result['mapping'][1]['end_delta_ms'], 7510)
        self.assertEqual(result['timing_check']['timing_matches'], 3)

    def test_global_offset_is_rejected_even_when_most_cues_match(self):
        shifted = self.srt('global.srt', [
            (1, '00:00:08,800', '00:00:09,800', 'Reviewed one'),
            (2, '00:00:10,800', '00:00:11,800', 'Reviewed two'),
            (3, '00:00:12,800', '00:00:13,800', 'Reviewed three'),
        ])
        result = timing.compare_timings(self.reference, shifted)
        self.assertFalse(result['ok'])
        self.assertEqual(result['timing_matches'], 2)
        self.assertEqual([x['cue'] for x in result['mismatches']], [2])
        self.assertEqual(result['mismatches'][0]['start_error_ms'], -340)
        self.assertEqual(result['mismatches'][0]['end_error_ms'], 290)

    def test_reviewed_text_line_breaks_markers_and_screen_cue_survive(self):
        self.bind()
        self.assertEqual([c.lines for c in parse_srt(self.output)],
                         [c.lines for c in parse_srt(self.prepared)])
        self.assertEqual(len(parse_srt(self.output)), 3)
        self.assertIn('МЕСТО ВСТРЕЧИ', self.output.read_text())

    def test_baseline_formatting_case_and_line_breaks_do_not_block_binding(self):
        self.assertEqual(self.bind()['normalized_baseline_reference_text_matches'], 3)

    def test_source_bytes_and_historic_preparation_are_not_modified(self):
        paths = [self.baseline, self.reference, self.prepared]
        before = {p: p.read_bytes() for p in paths}
        self.bind()
        self.assertEqual(before, {p: p.read_bytes() for p in paths})

    def test_changed_negation_in_reference_fails_before_output(self):
        self.reference.write_text(self.reference.read_text().replace('Он не придёт.', 'Он придёт.'))
        with self.assertRaisesRegex(ValueError, 'text mismatch.*2'):
            self.bind()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_same_count_but_reordered_content_is_not_ordinally_guessed(self):
        text = self.reference.read_text().replace('Стой!', 'Он не придёт.').replace('Место\nвстречи', 'Стой!')
        self.reference.write_text(text)
        with self.assertRaisesRegex(ValueError, 'text mismatch'):
            self.bind()

    def test_different_counts_require_an_explicit_reviewed_mapping(self):
        self.reference.write_text(self.reference.read_text().split('\n\n3\n')[0] + '\n')
        with self.assertRaisesRegex(ValueError, 'cue count'):
            self.bind()
        self.assertFalse(self.output.exists())

    def test_previously_retimed_preparation_is_not_silently_shifted_again(self):
        self.prepared.write_text(self.prepared.read_text().replace('00:00:01,000', '00:00:01,100').replace('00:00:02,000', '00:00:02,100'))
        with self.assertRaisesRegex(ValueError, 'prepared timing.*1'):
            self.bind()

    def test_empty_track_is_not_a_successful_zero_cue_binding(self):
        self.baseline.write_text('')
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.bind()

    def test_bad_numbering_and_nonpositive_spans_fail(self):
        for old, new in [('1\n', '2\n'), ('00:00:09,800', '00:00:08,000')]:
            with self.subTest(new=new):
                before = self.reference.read_text()
                self.reference.write_text(before.replace(old, new, 1))
                with self.assertRaises(ValueError):
                    self.bind()
                self.reference.write_text(before)

    def test_intentional_overlap_is_preserved_and_reported(self):
        self.reference.write_text(self.reference.read_text().replace('00:00:09,800', '00:00:12,000'))
        result = self.bind()
        self.assertTrue(result['timing_check']['ok'])
        self.assertEqual(len(result['timing_check']['reference_overlap_warnings']), 1)
        self.assertEqual(parse_srt(self.output)[0].end_ms, 12000)

    def test_no_overwriting_output_or_existing_report(self):
        for protected in [self.output, self.report]:
            with self.subTest(protected=protected.name):
                protected.write_text('user data')
                with self.assertRaises(FileExistsError):
                    self.bind()
                self.assertEqual(protected.read_text(), 'user data')
                other = self.report if protected == self.output else self.output
                self.assertFalse(other.exists())
                protected.unlink()

    def test_output_cannot_replace_an_input_or_share_report_path(self):
        with self.assertRaises(ValueError):
            self.bind(output=self.baseline)
        with self.assertRaises(ValueError):
            self.bind(report=self.output)

    def test_report_hashes_describe_exact_inputs_and_result_not_audio_proof(self):
        result = self.bind()
        self.assertEqual(result, json.loads(self.report.read_text()))
        for key, path in [('baseline', self.baseline), ('reference', self.reference),
                          ('prepared', self.prepared), ('output', self.output)]:
            self.assertEqual(result[key]['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result[key]['bytes'], path.stat().st_size)
        self.assertFalse(result['audio_verified'])
        self.assertFalse(result['player_revision_verified'])

    def test_check_cli_returns_nonzero_for_a_single_wrong_end(self):
        self.bind()
        good = subprocess.run([sys.executable, str(SCRIPTS/'subtitle_timing.py'), 'check', str(self.reference), str(self.output)], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.output.write_text(self.output.read_text().replace('00:00:11,510', '00:00:11,511'))
        bad = subprocess.run([sys.executable, str(SCRIPTS/'subtitle_timing.py'), 'check', str(self.reference), str(self.output)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)['mismatches'][0]['end_error_ms'], 1)

    def test_bind_cli_and_check_report_are_usable_without_dependencies(self):
        command = [sys.executable, str(SCRIPTS/'subtitle_timing.py'), 'bind',
                   '--baseline', str(self.baseline), '--reference', str(self.reference),
                   '--prepared', str(self.prepared), '--output', str(self.output), '--report', str(self.report)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        check_report = self.root/'check.json'
        result = subprocess.run([sys.executable, str(SCRIPTS/'subtitle_timing.py'), 'check',
                                 str(self.reference), str(self.output), '--report', str(check_report)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(check_report.read_text())['ok'])

    def test_no_success_receipt_when_written_span_fails_readback(self):
        write = timing.write_new_files

        def corrupt_output(payloads):
            changed = [(path, payload.replace(b'00:00:11,510', b'00:00:11,511'))
                       for path, payload in payloads]
            write(changed)

        with patch.object(timing, 'write_new_files', side_effect=corrupt_output):
            with self.assertRaisesRegex(ValueError, 'readback'):
                self.bind()
        self.assertFalse(self.report.exists())

    def test_check_detects_count_mismatch_without_modifying_files(self):
        self.bind()
        self.output.write_text(self.output.read_text().split('\n\n3\n')[0] + '\n')
        before = self.output.read_bytes()
        result = timing.compare_timings(self.reference, self.output)
        self.assertFalse(result['ok'])
        self.assertIn('cue count differs', result['errors'][0])
        self.assertEqual(self.output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
