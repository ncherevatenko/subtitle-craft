#!/usr/bin/env python3
"""Deterministic SRT audit and validation helpers.

The audit mode intentionally produces review prompts rather than automatic
translation verdicts. The validate mode checks release invariants without
rewriting the subtitle file.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys


TIMESTAMP_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})$"
)
NUMBER_RE = re.compile(r"(?<!\w)\d[\d,.'’]*(?:\.\d+)?(?!\w)")
EN_REGISTER_RE = re.compile(
    r"\b(?:fuck(?:ed|er|ing|s)?|shit(?:ty)?|cunt|cock|dick|pussy|"
    r"asshole|bitch|bastard|orgasm|blowjob|handjob|horny)\b",
    re.IGNORECASE,
)
RU_REGISTER_RE = re.compile(
    r"(?:\b[а-яё]*(?:еб|ёб|ху[йяею]|пизд)[а-яё]*\b|"
    r"\b(?:бляд\w*|бля|дерьм\w*|говн\w*|сран\w*|долбан\w*|"
    r"хрен\w*|сука|мудак\w*|трах\w*|оргазм\w*|сиськ\w*|дроч\w*)\b|"
    r"\b(?:твою мать|мать твою)\b)",
    re.IGNORECASE,
)
NON_DIALOGUE_RE = re.compile(
    r"^\s*(?:\*[^*]+\*|\[[^]]+\]|\([^)]*music[^)]*\))\s*$",
    re.IGNORECASE,
)
MUSIC_SPAN_RE = re.compile(r"[♪♫][^♪♫]*[♪♫]")
TAG_RE = re.compile(r"</?[^>]+>|\{\\[^}]+\}")


@dataclass(frozen=True)
class Cue:
    index: int
    start: str
    end: str
    start_ms: int
    end_ms: int
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return " / ".join(self.lines)

    @property
    def visible_lines(self) -> tuple[str, ...]:
        return tuple(TAG_RE.sub("", line) for line in self.lines)


class SrtParseError(ValueError):
    pass


def timestamp_ms(parts: tuple[str, ...]) -> int:
    hours, minutes, seconds, millis = map(int, parts)
    if minutes > 59 or seconds > 59:
        raise SrtParseError(f"invalid clock value: {':'.join(parts)}")
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def parse_srt(path: Path) -> list[Cue]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SrtParseError(f"{path}: not valid UTF-8: {exc}") from exc
    blocks = re.split(r"\r?\n\s*\r?\n", raw.strip()) if raw.strip() else []
    cues: list[Cue] = []
    for position, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3:
            raise SrtParseError(f"{path}: block {position} has fewer than 3 lines")
        if not lines[0].strip().isdigit():
            raise SrtParseError(f"{path}: block {position} has invalid index {lines[0]!r}")
        match = TIMESTAMP_RE.fullmatch(lines[1].strip())
        if not match:
            raise SrtParseError(f"{path}: block {position} has invalid timestamp {lines[1]!r}")
        values = match.groups()
        start_ms = timestamp_ms(values[:4])
        end_ms = timestamp_ms(values[4:])
        cues.append(
            Cue(
                index=int(lines[0].strip()),
                start=lines[1].split(" --> ")[0],
                end=lines[1].split(" --> ")[1],
                start_ms=start_ms,
                end_ms=end_ms,
                lines=tuple(lines[2:]),
            )
        )
    return cues


def normalize_number(value: str) -> str:
    return re.sub(r"[,.'’]", "", value)


def numbers(text: str) -> set[str]:
    return {normalize_number(item) for item in NUMBER_RE.findall(text)}


def is_dialogue(cue: Cue) -> bool:
    # Lyrics and speech can share a cue, even a single line. Remove only
    # closed music spans; retain ambiguous unclosed markers for review.
    remainder = MUSIC_SPAN_RE.sub("", "\n".join(cue.visible_lines))
    return any(
        line.strip() and not NON_DIALOGUE_RE.fullmatch(line)
        for line in remainder.splitlines()
    )


def overlaps(source: Cue, target: Cue, tolerance_ms: int) -> bool:
    return (
        target.start_ms <= source.end_ms + tolerance_ms
        and target.end_ms >= source.start_ms - tolerance_ms
    )


def validate(args: argparse.Namespace) -> int:
    path = Path(args.srt).expanduser().resolve()
    try:
        cues = parse_srt(path)
    except (OSError, SrtParseError) as exc:
        print(f"ERROR {exc}")
        print("errors=1 warnings=0")
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    previous: Cue | None = None
    for position, cue in enumerate(cues, 1):
        if cue.index != position:
            errors.append(f"cue {position}: index is {cue.index}, expected {position}")
        if cue.end_ms <= cue.start_ms:
            errors.append(f"cue {cue.index}: end is not after start")
        if previous is not None:
            if cue.start_ms < previous.start_ms:
                errors.append(f"cue {cue.index}: start time is not monotonic")
            if cue.start_ms < previous.end_ms:
                message = (
                    f"cue {previous.index}->{cue.index}: overlap "
                    f"{previous.end_ms - cue.start_ms} ms"
                )
                (errors if args.strict_overlaps else warnings).append(message)
        if not any(line.strip() for line in cue.visible_lines):
            errors.append(f"cue {cue.index}: empty visible text")
        if len(cue.lines) > args.max_lines:
            errors.append(
                f"cue {cue.index}: {len(cue.lines)} text lines, maximum {args.max_lines}"
            )
        for line_number, line in enumerate(cue.visible_lines, 1):
            if len(line) > args.max_chars:
                errors.append(
                    f"cue {cue.index}.{line_number}: {len(line)} visible characters, "
                    f"maximum {args.max_chars}"
                )
        previous = cue

    if args.expected_cues is not None and len(cues) != args.expected_cues:
        errors.append(f"cue count is {len(cues)}, expected {args.expected_cues}")

    for message in errors:
        print(f"ERROR {message}")
    for message in warnings:
        print(f"WARNING {message}")
    print(f"file={path} cues={len(cues)} errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


def audit(args: argparse.Namespace) -> int:
    source_path = Path(args.source).expanduser().resolve()
    target_path = Path(args.target).expanduser().resolve()
    try:
        source = parse_srt(source_path)
        target = parse_srt(target_path)
    except (OSError, SrtParseError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    lines: list[str] = []
    counts = {"dialogue": 0, "missing": 0, "numeric": 0, "register": 0}
    for source_cue in source:
        if not is_dialogue(source_cue):
            continue
        counts["dialogue"] += 1
        matches = [
            cue
            for cue in target
            if overlaps(source_cue, cue, args.tolerance_ms)
        ]
        target_text = " | ".join(cue.text for cue in matches)
        flags: list[str] = []
        if not matches:
            flags.append("MISSING_TARGET")
            counts["missing"] += 1
        source_numbers = numbers(source_cue.text)
        target_numbers = numbers(target_text)
        if source_numbers and not source_numbers.issubset(target_numbers):
            flags.append(
                "NUMERIC " + ",".join(sorted(source_numbers - target_numbers))
            )
            counts["numeric"] += 1
        if EN_REGISTER_RE.search(source_cue.text) and not (
            RU_REGISTER_RE.search(target_text) or EN_REGISTER_RE.search(target_text)
        ):
            flags.append("REGISTER")
            counts["register"] += 1
        if flags or args.all:
            lines.append(
                f"{source_cue.start} EN[{source_cue.index}] {source_cue.text}"
            )
            lines.append(
                "  RU "
                + (
                    " | ".join(f"[{cue.index}] {cue.text}" for cue in matches)
                    if matches
                    else "—"
                )
            )
            lines.append("  FLAGS " + (", ".join(flags) if flags else "—"))
            lines.append("")

    summary = (
        f"source_dialogue={counts['dialogue']} missing={counts['missing']} "
        f"numeric={counts['numeric']} register={counts['register']}"
    )
    report = "\n".join(lines) + ("\n" if lines else "") + summary + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.write_text(report, encoding="utf-8")
        print(f"output={output} {summary}")
    else:
        print(report, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate one SRT")
    validate_parser.add_argument("srt")
    validate_parser.add_argument("--expected-cues", type=int)
    validate_parser.add_argument("--max-lines", type=int, default=2)
    validate_parser.add_argument("--max-chars", type=int, default=42)
    validate_parser.add_argument(
        "--strict-overlaps",
        action="store_true",
        help="treat overlapping consecutive cues as errors instead of warnings",
    )
    validate_parser.set_defaults(handler=validate)

    audit_parser = subparsers.add_parser("audit", help="align source and target SRT")
    audit_parser.add_argument("source")
    audit_parser.add_argument("target")
    audit_parser.add_argument("--output")
    audit_parser.add_argument("--tolerance-ms", type=int, default=250)
    audit_parser.add_argument("--all", action="store_true", help="include unflagged cues")
    audit_parser.set_defaults(handler=audit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
