#!/usr/bin/env python3
"""Bind one-to-one SRT tracks safely, or compare every resulting time span.

No media probing, playback, publishing, or audio/synchronization verdict. The
reference must already be identified as the correct completed-release track.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import sys
import unicodedata

from subtitle_audit import Cue, parse_srt


def fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def visible_text(cue: Cue) -> str:
    # Ignore presentation differences, not punctuation, numbers or negation.
    text = html.unescape(' '.join(cue.visible_lines))
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def read_track(path: Path) -> list[Cue]:
    cues = parse_srt(path)
    if not cues:
        raise ValueError(f'{path}: empty subtitle track')
    previous = None
    for position, cue in enumerate(cues, 1):
        if cue.index != position:
            raise ValueError(f'{path}: nonsequential index at cue {position}')
        if cue.end_ms <= cue.start_ms:
            raise ValueError(f'{path}: nonpositive span at cue {position}')
        if previous is not None and cue.start_ms < previous.start_ms:
            raise ValueError(f'{path}: nonmonotonic start at cue {position}')
        if not visible_text(cue):
            raise ValueError(f'{path}: empty visible text at cue {position}')
        previous = cue
    return cues


def overlap_warnings(cues: list[Cue]) -> list[dict]:
    active = []
    warnings = []
    for cue in cues:
        active = [other for other in active if other.end_ms > cue.start_ms]
        for other in active:
            warnings.append({'earlier_cue': other.index, 'cue': cue.index,
                             'overlap_ms': min(other.end_ms, cue.end_ms) - cue.start_ms})
        active.append(cue)
    return warnings


def compare_cues(reference: list[Cue], candidate: list[Cue]) -> dict:
    mismatches = []
    matches = 0
    for expected, actual in zip(reference, candidate):
        if (expected.start_ms, expected.end_ms) == (actual.start_ms, actual.end_ms):
            matches += 1
        else:
            mismatches.append({'cue': expected.index,
                               'expected_start': expected.start, 'expected_end': expected.end,
                               'actual_start': actual.start, 'actual_end': actual.end,
                               'start_error_ms': actual.start_ms - expected.start_ms,
                               'end_error_ms': actual.end_ms - expected.end_ms})
    errors = []
    if len(reference) != len(candidate):
        errors.append(f'cue count differs: reference={len(reference)} candidate={len(candidate)}')
    return {'ok': not errors and not mismatches,
            'reference_cues': len(reference), 'candidate_cues': len(candidate),
            'timing_matches': matches, 'mismatches': mismatches, 'errors': errors,
            'reference_overlap_warnings': overlap_warnings(reference),
            'candidate_overlap_warnings': overlap_warnings(candidate)}


def ensure_unchanged(paths: list[Path], before: list[dict]) -> None:
    if [fingerprint(path) for path in paths] != before:
        raise ValueError('An input changed during timing verification; retry with stable files')


def compare_timings(reference: Path, candidate: Path) -> dict:
    reference, candidate = Path(reference).resolve(), Path(candidate).resolve()
    paths = [reference, candidate]
    before = [fingerprint(path) for path in paths]
    result = compare_cues(read_track(reference), read_track(candidate))
    ensure_unchanged(paths, before)
    result.update(reference=before[0], candidate=before[1],
                  scope='Time-span equality only; cue correspondence needs separate binding evidence',
                  audio_verified=False, player_revision_verified=False)
    return result


def protect_destinations(destinations: list[Path], inputs: list[Path]) -> None:
    resolved = [path.resolve() for path in destinations]
    if len(set(resolved)) != len(resolved) or set(resolved) & set(inputs):
        raise ValueError('Output/report must be distinct from each other and all inputs')
    for path in destinations:
        if path.exists() or path.is_symlink():
            raise FileExistsError(f'Refusing to overwrite existing artifact: {path}')
        if not path.parent.is_dir():
            raise ValueError(f'Artifact parent directory does not exist: {path.parent}')


def write_new_files(payloads: list[tuple[Path, bytes]]) -> None:
    created = []
    try:
        for path, payload in payloads:
            # Exclusive creation also protects against a destination appearing
            # after the preflight. Roll back only files created by this call.
            with path.open('xb') as stream:
                created.append(path)
                stream.write(payload)
    except Exception:
        for path in created:
            path.unlink()
        raise


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def bind_tracks(*, baseline: Path, reference: Path, prepared: Path,
                output: Path, report: Path) -> dict:
    baseline, reference, prepared = [Path(p).resolve() for p in (baseline, reference, prepared)]
    output, report = Path(output).absolute(), Path(report).absolute()
    paths = [baseline, reference, prepared]
    protect_destinations([output, report], paths)
    before = [fingerprint(path) for path in paths]
    old, actual, reviewed = [read_track(path) for path in paths]
    if not len(old) == len(actual) == len(reviewed):
        raise ValueError('cue count differs; splits, merges or cut changes need a reviewed explicit mapping')
    mapping = []
    blocks = []
    for base, ref, text in zip(old, actual, reviewed):
        if visible_text(base) != visible_text(ref):
            raise ValueError(f'baseline/reference text mismatch at cue {base.index}; do not guess ordinal mapping')
        if (base.start_ms, base.end_ms) != (text.start_ms, text.end_ms):
            raise ValueError(f'prepared timing differs from baseline at cue {base.index}; do not retime twice')
        mapping.append({'cue': base.index, 'baseline_start': base.start, 'baseline_end': base.end,
                        'reference_start': ref.start, 'reference_end': ref.end,
                        'start_delta_ms': ref.start_ms - base.start_ms,
                        'end_delta_ms': ref.end_ms - base.end_ms})
        blocks.append(f'{text.index}\n{ref.start} --> {ref.end}\n' + '\n'.join(text.lines) + '\n')
    payload = '\n'.join(blocks).encode('utf-8')
    ensure_unchanged(paths, before)
    # Independent arithmetic check before writing, followed by actual-file
    # readback below. Never infer all timings from a modal/common shift.
    rebound = [Cue(c.index, r.start, r.end, r.start_ms, r.end_ms, c.lines)
               for c, r in zip(reviewed, actual)]
    result = {'schema_version': 1, 'state': 'TIMING_BOUND',
              'baseline': before[0], 'reference': before[1], 'prepared': before[2],
              'output': {'path': str(output.resolve()), 'bytes': len(payload),
                         'sha256': hashlib.sha256(payload).hexdigest()},
              'normalized_baseline_reference_text_matches': len(old),
              'normalization': 'Visible text: strip tags, decode HTML entities, NFC, casefold, whitespace; punctuation and digits retained',
              'mapping': mapping,
              'start_offset_histogram_ms': dict(Counter(str(x['start_delta_ms']) for x in mapping)),
              'end_offset_histogram_ms': dict(Counter(str(x['end_delta_ms']) for x in mapping)),
              'timing_check': compare_cues(actual, rebound),
              'prepared_text_and_line_breaks_preserved': True,
              'scope': 'One-to-one text binding and per-cue timing transfer only; release identity and audio anchors still required',
              'audio_verified': False, 'player_revision_verified': False}
    write_new_files([(output, payload)])
    written = read_track(output)
    if not compare_cues(actual, written)['ok'] or [c.lines for c in written] != [c.lines for c in reviewed]:
        raise ValueError('Written artifact failed timing/text readback; do not publish it')
    if fingerprint(output) != result['output']:
        raise ValueError('Written artifact hash mismatch; do not publish it')
    ensure_unchanged(paths, before)
    # Emit a successful binding receipt only after actual-file readback.
    write_new_files([(report, json_bytes(result))])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    bind = commands.add_parser('bind', help='verified one-to-one transfer; new staged artifacts only')
    for field in ('baseline', 'reference', 'prepared', 'output', 'report'):
        bind.add_argument('--' + field, type=Path, required=True)
    check = commands.add_parser('check', help='read-only comparison of every cue start and end')
    check.add_argument('reference', type=Path)
    check.add_argument('candidate', type=Path)
    check.add_argument('--report', type=Path, help='optional new JSON report; never overwrite')
    args = parser.parse_args()
    try:
        if args.command == 'bind':
            result = bind_tracks(baseline=args.baseline, reference=args.reference,
                                 prepared=args.prepared, output=args.output, report=args.report)
            print(json.dumps({'ok': True, 'cues': len(result['mapping']),
                              'output': result['output'], 'report': str(args.report.resolve())}, ensure_ascii=False))
            return 0
        result = compare_timings(args.reference, args.candidate)
        if args.report:
            protect_destinations([args.report], [args.reference.resolve(), args.candidate.resolve()])
            write_new_files([(args.report, json_bytes(result))])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['ok'] else 1
    except (OSError, ValueError) as exc:
        print(f'ERROR {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
