# NFR-2 / NFR-3 implementation and acceptance

This document records the current repository contract and the evidence CI checks. It does not claim that the requirements have received team approval or independent acceptance.

## NFR-2: robustness and auditability

The pipeline is best-effort by default. Recoverable Git, scanner, and TODO failures are represented by machine-readable reason codes and propagated to `AnalysisResult.stats.degradations`; file-specific codes also appear in `FileResult.limitations`. `files_degraded` counts distinct affected file paths, while `degradations_by_code` counts diagnostic events. Repository-wide failures have a null path and do not count as degraded files. Strict mode rejects any recorded diagnostic, including one outside a top-N output limit. Member 4's five deep-history analyses also provide `*_with_degradations()` results and flag empty repositories and shallow-history boundaries; compatibility APIs warn if callers choose an API that only returns the result value.

The fault suite covers non-ASCII and deep paths, binary/large/syntax-invalid/alternate-encoding files, symlinks where supported, empty and non-Git repositories, shallow clones, unreadable files, and Git object failures. Platform-dependent symlink checks skip when the host cannot create links. Tests also verify that failures do not expose host-specific absolute paths in stable diagnostic details, and that HTML/JSON surface degradation information.

The tests verify representative fault classes and accounting invariants; they are not a proof of zero crashes for arbitrary repositories. File permission behavior differs under elevated accounts, so unreadability is tested by injected I/O failure. Strict-mode behavior is covered through pipeline and CLI regression tests.

## NFR-3: reproducibility and verifiability

`AnalysisResult.canonical()` produces compact UTF-8 JSON with recursively sorted object keys. It omits runtime clock fields (`analyzed_at`, `scanned_at`, `elapsed_ms`, and `stage_elapsed_ms`), rounds finite floating values to six decimal places, normalizes backslashes in path-valued fields, rejects NaN/infinity, and omits `repo_path` and `repo_urn` because they identify the checkout host/location. Array order remains meaningful and is made stable by path tie-breakers in file and folder rankings. `fingerprint()` is lowercase SHA-256 of this UTF-8 representation.

The frozen fixture test creates three synthetic Git histories with fixed author/committer dates and a fixed injected analysis clock. It checks repeatable fingerprints and checkout-path independence. CI runs the same contract on Windows and Linux with Python 3.10–3.12. The digest is a regression identifier within the normalized environment; the test does not require a platform-specific Git checkout to produce the same raw digest when working-tree normalization differs. These fixtures do not establish equivalence for arbitrary real repositories or every Git/Python version.

## Verification

Required PR checks include the complete pytest suite (including focused degradation/fingerprint and renderer contract tests), unused-import linting for changed NFR modules, and mypy on the changed core modules. The repository currently has broader Ruff and mypy findings outside this NFR scope, so those are not yet global CI gates. Browser interaction runs on Linux/Python 3.12; the headless Chrome check is separate from the cross-platform core matrix.

The remaining acceptance decisions are the final agreed list of NFR-2 fault classes, whether strict mode should treat every warning as fatal, and the supported cross-platform/tool-version equivalence boundary. No user study or performance claim is implied by these engineering tests.
