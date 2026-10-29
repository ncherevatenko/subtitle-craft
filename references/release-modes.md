# Release modes and evidence

Use these boundaries when text preparation, a completed download, and playback
are separate stages. Adapt the filenames to the existing workflow rather than
creating another downloader or taking ownership of its state.

## Text preparation

Prepare useful text while the media is unavailable, without claiming AV proof.

- Preserve each source, its origin, release label, encoding, and checksum.
- Review all spoken cues in the agreed range twice. Preserve target-only text
  and record unresolved source wording with timestamps and cue IDs.
- Keep staged output separate from a final media-bound sidecar. Use a stage
  such as `PREPARED` when the surrounding workflow uses that convention.
- Preserve a recorded preparation artifact and its checksum when continuing
  against the completed media. Write a distinct release-bound revision and
  report rather than overwriting the evidence for the earlier stage.
- Record reviewed source ranges, dialogue count, retained target-only cues,
  excluded non-dialogue cues, correction counts, and format diagnostics.
- Set audio and media synchronization coverage to unverified when no media was
  inspected. A successful SRT validator isn't a translation or sync verdict.
- Don't open a changing download, edit downloader locks or state, reconfigure
  the network, or revive a cancelled title as a subtitle-preparation step.

## Bind to the completed release

Use the actual completed file after the workflow's readiness proof is available.

1. Check the release identity, exact selected file, size, and available proof.
   Keep torrent metadata info hashes distinct from a whole-file checksum.
2. Inspect the real streams. Extract full English, Russian, SDH, and forced
   tracks as relevant, preserving their original files.
3. Compare the prepared source against embedded text and timings. Document
   exact matches, offsets, edition differences, and missing information.
4. Check disputed lines and timing anchors near the beginning, middle, and end
   using source audio. Exact text binding doesn't resolve a caption error such
   as a wrong object or an incorrect equipment term.
5. Record each sampled interval and evidence type. Label ASR-only comparison
   as such. Count repeated channel or model variants only once in unique audio
   coverage, and don't imply a full listening or visual pass.
6. If a phrase remains unclear after a bounded retry, preserve its clear part
   and explicitly mark the rest. List both visible placeholders and tentative
   interpretations in the report. A contextual translation isn't exact wording
   recovery, even when several existing translations agree.

Read separate forced tracks before publishing. Retain plot-relevant messages,
signs, product labels, and foreign dialogue, with mappings to their source cues.
Document intentionally excluded song or sound captions separately. Confirm
important or ambiguous screen text on extracted stills when necessary.

### One-to-one timing transfer

Use `scripts/subtitle_timing.py bind` when a same-language unedited baseline
and the completed release's reference track have the same cue count and
corresponding visible text. The reviewed preparation must still have the
baseline's original timings. This verifies correspondence before using cue
positions; equal counts or cue numbers alone are not a mapping.

```bash
python3 scripts/subtitle_timing.py bind \
  --baseline original.ru.srt --reference embedded.ru.srt \
  --prepared reviewed.pending-av.srt \
  --output reviewed.release-bound.srt --report timing-binding.json
python3 scripts/subtitle_timing.py check \
  embedded.ru.srt reviewed.release-bound.srt --report timing-check.json
```

`bind` copies each reference start **and** end separately, retaining all
reviewed text, line breaks, uncertainty markers, and target-only cues. It
refuses mismatched text, counts, already-retimed preparation, and existing
output/report paths. Presentation normalization ignores tags, case, and
whitespace, not punctuation, numbers, or negation. On refusal, inspect the
difference; don't weaken the check or force a uniform shift. Splits, merges,
added forced cues, or genuinely different cuts need an explicitly reviewed
mapping instead of this one-to-one helper.

`check` is read-only apart from an optional new report; any different start,
end, or count returns a nonzero exit code. Use it again after final edits and
on the published sidecar when one-to-one correspondence is still valid.
Reports include hashes, every transferred span, offset distributions, and
overlap warnings. They prove timing equality, **not** audio synchronization,
translation accuracy, or a loaded player revision; the release identity and
audio anchors above remain necessary. Run the normal SRT validator as well.

## Validate and publish

Publish only the reviewed artifact and state its remaining limitations.

- Apply corrections through a reproducible map. Preserve original dialogue
  timings unless an independently verified sync issue requires a change.
- Rebuild and reverse-check every new correction after its last edit, including
  adjacent cues of the same utterance and related speaker agreement.
- Explain any count change: retained dialogue plus added screen text minus
  documented exclusions. Don't force unequal source tracks into equal counts.
- Validate numbering, timestamps, visible line lengths, and expected count.
  Inspect and report warnings. Deliberate dialogue/screen overlaps can remain;
  don't report them as zero warnings or pretend they were tested in a player.
- Save a report with staged and sidecar paths, byte counts, SHA-256 values,
  actual text/audio/sync coverage, corrections by pass, and unresolved cues.
- Preserve a different existing sidecar before replacement. Read back the
  published file and compare its bytes with the validated staged output.
- Use `SUBTITLES_READY` or the existing equivalent only for the media-bound
  artifact. Its limitations and sampled coverage must remain visible.

## Fast portions and playback

Honor an explicit request to start an approved first portion without implying
that the remainder is finished.

- Report the exact reviewed prefix, the status of the remainder, and whether a
  provisional full-length track or a prefix-only track will be loaded.
- A prefix must pass the relevant text and sync checks for that portion.
  `PREPARED` or `SUBTITLES_READY` alone doesn't grant playback authorization.
- Before an authorized launch or reload, inspect the current item, position,
  paused state, and tracks. Perform one intended launch or reload; don't send
  duplicate open commands because the first response was slow.
- If the user requests continuity, preserve position and paused state, as well
  as the requested audio track. Don't assume reopening starts at the same point.
- Replacing a disk file doesn't prove the player reread it. Verify the selected
  external subtitle path or revision acknowledgment and a distinctive rendered
  cue when possible. Distinguish requested settings from observed playback.
- Never claim `PLAYBACK_STARTED`, a loaded revision, or successful rendering
  from a saved SRT, an open command, or a desired track setting alone.

If the player cannot expose the loaded subtitle revision, report that limit
and ask for a visible cue check rather than claiming certainty.

### CLI evidence and recovery

Use shell control when the user requests it. Separate a successful launch
command, observed playback, a loaded subtitle revision, and visible rendering.

1. Inspect the existing player before sending an open command. With an existing
   VLC RC connection, query `status`, `get_time`, `atrack`, and `strack` without
   arguments; these read the current item, position, and track selections.
   Use the configured local endpoint rather than assuming a fixed port.
2. If the connection is refused, inspect the process separately, for example
   with `pgrep -x VLC` on macOS. Connection refusal means the control endpoint
   is unavailable, not that VLC is closed. If VLC is running, recover its state
   through an available read-only interface before deciding what to change.
   If process inspection is denied or inconclusive, report unknown state.
3. If the correct item is already playing with the requested revision, don't
   reopen it. If VLC is confirmed closed and launch is authorized, open it once
   with the exact media and subtitle paths. Prefer explicit `--sub-file` and
   `--no-sub-autodetect-file` when supported by the installed VLC. Inspect local
   help if the required option or control behavior is uncertain.
4. Map the actual source stream to the launch option, then verify the selected
   track after loading. A container stream index, a zero-based audio ordinal,
   and a VLC runtime elementary-stream ID aren't interchangeable. Don't reuse
   another release's numbers or infer language from its track order.
5. Wait for loading and repeat read-only queries for a bounded startup period.
   A first response of `stopped`, an incomplete track list, or a slow open
   command isn't evidence that the launch failed. Don't send another open,
   seek, toggle pause, or kill the player to make a check pass. On timeout,
   inspect the same process and its current launch log and report uncertainty.

Keep evidence scoped to the current request and player input:

- Save a new launch or reload receipt with its direct authorization, release
  identity, exact paths, subtitle checksum, and observation time. Preserve old
  receipts. Repeating the same request must not cause another launch; a later
  explicit request after the player closes is a separate action.
- For a new process, use a fresh log or record the pre-action log boundary.
  Never reuse an earlier session's load messages as current proof. Don't
  enable new player interfaces by restarting ongoing playback without approval.
- Bind the explicit path and checksum to the current input's subtitle-load
  event and then to the selected external track in a fresh readback. A matching
  cue count alone isn't a revision identity. An unchanged on-disk checksum
  alone doesn't establish which version an existing process has cached.
- Record the current media, playing or paused state, position, actual selected
  audio, selected subtitle, and the evidence supporting the loaded revision.
  If a reload was requested, verify continuity and the new revision separately.
  Replacing the sidecar on disk isn't a reload acknowledgment.
- Report only the proven level: `command sent`, `playback observed`,
  `external revision acknowledged`, or `rendered cue confirmed`. Decoder or
  video-output logs aren't visual confirmation that a subtitle was drawn.
  When CLI evidence binds the loaded revision but no frame was inspected,
  state that distinction if the user asks how it was verified.

Preparation for another title doesn't authorize switching or interrupting the
current film. Inspect and prepare its files separately, without changing VLC.
