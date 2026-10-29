---
name: subtitle-translation-audit
description: >-
  Prepare or audit bilingual SRT subtitles, repair meaning and register, check
  disputed lines against available source audio, and validate a release-bound
  sidecar. Use for episode or film translation review and timestamp-specific
  corrections, not ordinary audio-only transcription.
---

# Subtitle translation audit

Produce natural target-language subtitles without losing any claim, relationship,
joke, technical detail, or level of explicitness in the source.

The central rule is: **a natural-sounding translation is not necessarily an
accurate translation**. For every dialogue cue, verify what was asserted before
judging the wording.

## Choose the permitted review mode

Distinguish text preparation from verification against a completed release.

- If the media is still downloading, prepare from preserved online or supplied
  subtitles. Don't probe or extract from changing media. Record the release
  identity and sources, and leave audio and video synchronization unverified.
- If the completed media is available and in scope, inspect it with `ffprobe`.
  Identify each audio, full subtitle, SDH, and forced track by actual stream
  index, language, and title. A requested language isn't a verified selection.
- If the user requests a fast first portion, review that portion and report its
  exact range. Don't label an unreviewed remainder as reviewed. Preparation
  alone doesn't authorize playback or a restart.

Read [release modes and evidence](references/release-modes.md) when preparing
before download completion, publishing a sidecar, or launching or reloading it.

## Establish the sources

Preserve the original extracted or downloaded files and their provenance.

1. Extract relevant tracks into a per-release work directory when media access
   is permitted. Keep the original target SRT untouched.
2. Prioritize audible source dialogue, then full source-language subtitles,
   source-language SDH, and the existing target translation. Exact agreement
   between online and embedded subtitles proves text binding, not that every
   caption correctly transcribes the audio. Several sites or release labels may
   redistribute the same caption master; their agreement isn't independent
   audio evidence. Treat an unverified target translation as a draft.
3. Align cues by time and scene context, never by cue number alone. Inspect
   separate forced tracks for messages, labels, signs, and foreign dialogue.
   Retain target-only information; don't delete it to match the English count.

Use `scripts/subtitle_audit.py audit` to generate a review view. It flags likely
coverage, numeric, and register problems, but flags are prompts for review rather
than automatic proof of an error.

```bash
python3 scripts/subtitle_audit.py audit source.srt target.srt --output audit.txt
```

The audit aligns by timestamp rather than cue number. Review every emitted flag;
do not automatically replace a translation merely to silence it.

## Perform the semantic pass

Review meaning before polishing the wording.

Review every spoken source cue. Exclude only music-only or sound-only material;
when lyrics or sound descriptions share a cue with speech, retain and review
the speech. Don't discard a whole cue merely because it contains a music symbol.
Record exclusions and any split-cue mapping. For each cue explicitly check:

- speaker, subject, object, and who acted on whom;
- negation, modality, uncertainty, tense, and whether an action is planned,
  ongoing, or completed;
- names, titles, organizations, locations, products, and named systems;
- every number, unit, currency, date, percentage, and distance;
- professional terminology and the scene-specific meaning of ambiguous words;
- idioms, wordplay, sexual humor, insults, and conversational intent;
- profanity and intensity. Preserve the source register unless the user asks
  for sanitization; do not replace explicit language with generic euphemisms;
- whether a source cue was merged into an adjacent target cue. Confirm that no
  clause disappeared during merging.

Read enough neighboring cues to understand the scene. Never translate an idiom
or operational term from a single isolated line when the surrounding exchange
changes its meaning.

For multi-cue utterances, track the speaker and addressee through the entire
turn. Correct every related verb, pronoun, and gender agreement, not just the
first cue. Use natural gender-neutral wording when the evidence is insufficient.

Reverse-check the physical action and its direction: an attack isn't a rescue,
reversing a car isn't holding on, opening isn't closing, and a current state
isn't a future plan. Don't resolve ambiguous equipment or vehicle terminology
from a plausible Russian sentence alone.

For slang and jokes, preserve the intended meaning and setup/payoff across the
scene. Don't interpret money slang as actual food, police slang as a place,
or a deliberately mistaken quotation as a correct one. A localized wordplay
must preserve the joke's function without adding factual claims or escalating
the profanity. Mark wording that still depends on audio instead of inventing it.

## Verify against audio

Extract a 15–30 second source-audio window and transcribe or inspect it when:

- the user names a timestamp;
- the translation is unusually generic or grammatically plausible but vague;
- the source subtitle conflicts with context or SDH;
- a proper name, number, idiom, joke, or operational term is uncertain;
- a line appears omitted or assigned to the wrong speaker;
- a correction would materially change the plot or a character's intent.

Use the `audio-transcription` skill when available. Automatic transcription is
supporting evidence, not authority. Compare it with source subtitles and scene
context, and distinguish direct listening from reviewing ASR output.

When ASR is garbled or conflicts with the captions, retry with an appropriate
cached model or a cleaner speech channel after checking the channel layout.
Don't treat repeated hallucinations, or agreement between related models, as
independent proof. Bound retries; preserve the recoverable fragment and mark
the unresolved portion with its cue and timestamp in the report.

Record the union of checked audio intervals, not the sum of repeated versions
of the same clip. Don't claim an audio check unless the audio was extracted and
the result inspected; don't call sampled ASR a full-episode listening pass.

## Apply changes reproducibly

Keep each correction reproducible and release artifacts distinct.

- Store corrections as a cue-number-to-text mapping applied to the untouched
  extracted target SRT. Do not hand-edit the generated output as the only copy
  of a correction.
- Preserve cue numbers and timings unless a synchronization problem has been
  independently confirmed. If adding forced screen text or splitting cues
  requires renumbering, preserve the original time spans and store the mapping.
- Preserve target-only screen text and foreign-language dialogue.
- Prefer concise, idiomatic lines, normally no more than two lines, but never
  delete meaning solely to satisfy a line-length preference.
- Write a reviewed output artifact and, when the established workflow requires
  it, copy an identical sidecar next to the video.

## Mandatory second pass

Check the generated artifact, not only the correction map.

After applying corrections, re-run the alignment against the improved SRT and
review it again from source to target. This pass must begin at any timestamp the
user previously identified and continue through the end of the requested range.

For each changed cue, reverse-check the final target text against the source:
list the source propositions mentally and confirm that every one survives. Pay
special attention to lines that already sounded natural before the edit; these
are the easiest omissions to miss.

After any later audio-driven edit, rebuild and read the entire affected
multi-cue utterance as continuous speech, including preposition/case and
speaker-gender links. Reverse-check its meaning and validate again. Record
these edits separately; don't silently keep the earlier artifact's checksum.

## Release gates

Completion must describe the artifact and evidence that actually exist.

Before reporting completion:

1. Confirm every dialogue cue in the requested range was reviewed.
2. Resolve or explicitly report every missing-target, numeric, register, and
   name-or-system review flag.
3. Run `scripts/subtitle_audit.py validate` on the generated SRT.
4. Confirm sequential numbering and valid timestamps. Reconcile the final
   count against retained dialogue, added screen text, and explicitly omitted
   non-dialogue cues. For a verified one-to-one reference track, run
   `scripts/subtitle_timing.py check` on every final time span, not just sampled
   cues or a common shift; see [release modes](references/release-modes.md).
   Confirm byte-identical output and published sidecar.
5. Re-open several high-risk changed scenes: user-reported timestamps, merged
   cues, idioms, proper names, numbers, and explicit dialogue.
6. Report total corrections separately from corrections added by a later pass.
   Distinguish genuine semantic errors from stylistic polishing.
7. Save the final paths, byte counts, checksums, coverage, and limitations.
   Launch or reload only if separately authorized, and verify the actual
   selected tracks and loaded revision before claiming they applied. A failed
   control connection doesn't establish that the player is closed; an early
   stopped state doesn't justify a second open command. See the CLI evidence
   and recovery procedure in [release modes](references/release-modes.md).

```bash
python3 scripts/subtitle_audit.py validate final.srt --expected-cues 1000
```

Overlapping cues are warnings by default because dialogue may legitimately
coexist with forced screen text. Use `--strict-overlaps` only when the requested
delivery format forbids simultaneous cues. Report the actual warning count and
its disposition, never zero warnings when deliberate overlaps remain. Numeric
and register flags are heuristic: written-out numbers, spaced thousands, and
inflected profanity can require manual disposition rather than a text change.

When summarizing changes, give representative before/after examples and explain
why they mattered. Do not describe all edits as errors when some were only
grammar, line breaking, or stylistic refinement.

Run the helpers' synthetic regression tests after changing their implementation:

```bash
python3 -m unittest discover -s tests -v
```

These tests verify parsing and diagnostic behavior, not semantic correctness.
