# Engineering process records

This directory holds the **primary working records** behind the process claims made in the
final report — the documents the team actually used while working, not polished
documentation written afterwards.

Two things to know before reading:

- **The record files are kept in their original Chinese.** They were written for internal use;
  translating them afterwards would make them look more finished than they are. The formal
  contracts (`docs/nfr.md`, `docs/evaluation-contract.md`, `docs/architecture.md`) are in
  English and are the authoritative versions.
- **These are plans, registers and sign-off sheets, not results.** Where a plan says "to do",
  it means it was to do at that moment. What was actually delivered is recorded in
  `docs/nfr.md`, `docs/evaluation-replay-result.md` and the git history.

## What is here

| File | What it records | Where it feeds the report |
|---|---|---|
| `sprint-3-plan.md` | Sprint 3 work packages (WP-S3-1…6), weekly schedule, acceptance checklist, risk table | §6.1 Sprint structure |
| `nfr-plan-and-assignment.md` | Measurable definitions of NFR-2/NFR-3, ten work packages, assignment table with effort estimates, PR split | §5, §6.2 Ownership |
| `defect-register.md` | Defect register: the P0 non-ASCII path failure, per-module detail, open semantic questions, already-fixed items, assignment advice | §6.3 Defect management |
| `code-review-sprint-1.md` | Sprint 1 code review findings | §6.4 Quality gates |
| `bug-report-m5-degradation.md` | Cross-module defect report: degradation counting never populated, `--strict` missing files outside `--limit` | §6.3 |
| `flaky-investigation.md` | Flaky-test investigation and resolution | §6.4 CI stability |
| `signoff-wp-s3-1.md` | Formal sign-off sheet for the three contested decisions (fault-class denominator, strict-mode semantics, cross-platform equivalence) | §5.3 Sign-off |
| `signoff-wp-s3-1-comparison.md` | The A/B comparison behind those three decisions | §5.1–5.2 Architecture decisions |
| `burndown.png` | Sprint burndown chart | §6.1 |

Generated from `presentations/build_burndown.py`.

## Presentations

`presentations/` holds the 7-minute demo deck and its supporting material.

| File | What it is |
|---|---|
| `demo-speech.pptx` | The 12-slide deck actually presented |
| `demo-speech-script.md` | Per-slide script: timing, on-screen description, spoken text, delivery notes |
| `demo-speech-script.pdf` | Printer-friendly version of the same |
| `qa-preparation.md` | Anticipated questions with vetted answers, plus a list of things **not** to say |
| `build_slides.py` | Rebuilds `demo-speech.pptx` from scratch (python-pptx) |
| `build_script_pdf.py` | Renders the script to PDF |
| `build_qa_pdf.py` | Renders the Q&A sheet to PDF |
| `build_burndown.py` | Renders the burndown chart |

The build scripts are included so the deliverables are **reproducible rather than
hand-assembled** — the same principle NFR-3 applies to the analysis output.

To rebuild, from the repository root:

```bash
pip install python-pptx
python docs/process/presentations/build_slides.py
python docs/process/presentations/build_script_pdf.py
python docs/process/presentations/build_burndown.py
```

## Not included, on purpose

| Excluded | Why |
|---|---|
| An earlier 11-slide deck | Superseded by the 12-slide version; it predates the evaluation results and would be misleading if read as current |
| A superseded draft of the scanner interface revision | Its content was folded into the authoritative `docs/scanner-interface.md` |
| Duplicate PDF/HTML renders | Same content as the markdown; kept in one format only |

## Relationship to the formal contracts

The records in this directory are the *working layer*. The *contract layer* — what the team
signed off as accepted behaviour — lives elsewhere and takes precedence:

| Question | Authoritative document |
|---|---|
| What counts as an accepted NFR, with which fault classes? | [`docs/nfr.md`](../nfr.md) |
| What exactly was evaluated, and by what method? | [`docs/evaluation-contract.md`](../evaluation-contract.md) |
| Why is the code layered this way, and which test guards what? | [`docs/architecture.md`](../architecture.md) |
| What did the evaluation actually return? | [`docs/evaluation-replay-result.md`](../evaluation-replay-result.md) |

Where a record and a contract disagree, the contract wins — and the disagreement itself is
worth noting, because it means one of them is out of date.

## Honest note on what these records show

They show that the project's two non-functional requirements were **not implemented as a
final polish**. NFR-2 came out of a defect (`defect-register.md`, P0 non-ASCII path) that made
the tool silently wrong; NFR-3 came out of the realisation that no evaluation is meaningful
without a deterministic output. The records also show the plans that slipped — Sprint 3's
evaluation plan went through a mid-course change from a participant study to a historical
replay, and both versions of that decision are on the record.
