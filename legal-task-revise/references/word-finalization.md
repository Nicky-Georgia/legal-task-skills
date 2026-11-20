# Word finalization and metadata

## Time measurement

The helper records active wall-clock intervals, including reading, research,
drafting, and QA. It is not a measure of human labor or continuous keyboard use.
Pause for waiting on a user, a suspended task, or a long idle external dependency;
ordinary processing needed for the task is part of the working session. Resume
when work resumes. Do not backfill invented intervals after forgetting to start
the clock. Report that limitation and use only a supported measurement.

```bash
python3 scripts/task_clock.py start --state /absolute/work/run/time.json
python3 scripts/task_clock.py pause --state /absolute/work/run/time.json
python3 scripts/task_clock.py resume --state /absolute/work/run/time.json
python3 scripts/task_clock.py status --state /absolute/work/run/time.json
python3 scripts/task_clock.py stop --state /absolute/work/run/time.json
```

The finalized clock's `active_seconds` is rounded to the nearest whole minute
for Word's `TotalTime`, which is an integer duration in minutes. Under 30 seconds
rounds to zero. Apply the same measured task duration to each revised file,
as the user requested; do not describe it as time uniquely spent editing each
individual file. The PDF's 3–5 hours is never substituted for actual time.

## Content and presentation first

Use the documents skill for editing and final rendering. Resolve its bundled
runtime through the workspace dependency loader. Render final content and inspect
every page, including headers, tables, footnotes, numbering, and page breaks.
Confirm amendments are localized and the rest of the work product remains usable.

Use structural checks as well as page images: comments, tracked changes, hidden
text, text boxes, custom properties, and fields may not appear in a PDF render.
Do not save changes from a renderer back over the final DOCX.

Remove only editorial artifacts introduced by this revision. Source comments or
redlines may be substantive evidence; check their origin and preserve them when
required. Accepting all revisions, deleting all hidden content, or deleting all
custom XML can destroy legally material content or document functionality.

## Final metadata pass

```bash
python3 scripts/finalize_docx.py \
  --input /absolute/work/run/checked.docx \
  --output /absolute/outputs/reference_answer/original-name.docx \
  --clock /absolute/work/run/time.json
```

The helper requires a stopped clock, a new output path, and a valid ordinary DOCX.
It changes only core/app properties and, when those parts are missing, their
content-type/relationship declarations. It sets creator and lastModifiedBy to
Renat Sigunov; modified time is actual UTC finalization time. Existing creation
time is retained. It does not backdate file-system timestamps or invent a
historical editing trail. Visible authors and signatories remain untouched.

Known generator-default description/application strings are removed rather than
replaced with a false claim that Microsoft Word authored the file. Other
properties remain intact. Manually inspect custom properties and template paths
for actual tool residue; remove specific residue using the documents workflow
only if it is not source content or a functional field dependency. Do not erase
all custom properties or authorship evidence indiscriminately.

The helper fails if it detects comments, revision elements, enabled tracking,
hidden text, macro content, or package signatures. It does not strip content.
For verified original source markup that must remain, use
`--allow-source-markup` only after recording its source and necessity in scratch.
That option is not a way to leave new agent edits or hidden notes in delivery.
Signatures/macros cannot be bypassed with this option; preserve the source and
make an appropriate separate unsigned, macro-free working copy if authorized.

For a verified [redline work product](redline-assignments.md), add
`--work-product-redline` to the same command. It requires actual native Word
revisions and permits their tracking settings and native comments while still
rejecting hidden text. Confirm that any comments are required work product or
material source annotations, and inspect their content and anchors before
finalization. This option does not substitute for baseline and accepted-state QA.

The post-write check verifies requested metadata and byte equality of every
non-metadata document part. This supports reusing the last successful content
render after metadata-only finalization; it is not a legal or visual check by
itself. Open/check final properties and ensure no unintended changes occurred.
If a subsequent tool resaves the DOCX, recheck metadata and content, and repeat
the relevant render/finalization steps as necessary.
