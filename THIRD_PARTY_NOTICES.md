# Third-party notices

## hotspot — scoring semantics reference

**Project:** `huangsam/hotspot` — <https://github.com/huangsam/hotspot>
**License:** MIT
**Copyright:** © 2025 Samuel Huang
**Verification snapshot:** commit `97b6d8ab` (2026-08-28), unmodified;
`core/algo/score.go` blob digest matches upstream `main`.

### What is used

The **scoring semantics** of the `hot`, `risk` and `roi` modes — their weights, the
normalisation caps, the exponential time decay and the debuff rules — are aligned with this
reference implementation so that scores remain comparable between the two tools. The alignment
is independent of executable code: githotmap is a Python codebase and does not vendor, link,
copy or translate hotspot's Go source.

### What is NOT used

- No source code, build artefacts or dependencies from hotspot are included in this
  distribution.
- No maintainer of hotspot contributed to or endorsed this project.
- The `complexity` mode shares only the name; its metric set differs (AST structure and SATD
  density rather than file size and staleness). Its scores, and those of the `refactor_now` and
  `legacy_debt` composites built on it, are **not** comparable with hotspot's.

### Attribution requirement

The MIT License requires the copyright notice and permission notice to be retained in copies
of *that* software. Because no hotspot code is redistributed here, this notice exists to make
the intellectual relationship explicit rather than to satisfy a redistribution obligation. The
full item-by-item comparison, including which weights are identical and what was changed on
purpose, is in [`docs/research/reference-alignment.md`](docs/research/reference-alignment.md)
and summarised in the README section "Relationship to the reference implementation".

---

## Other tools reviewed but not used

Projects examined during requirements research — CodeCharta, code-maat, churnmap, Radon,
PyDriller and Apache ECharts — contributed design observations only. None of their code,
data or configuration is included in this distribution. Details are in
[`docs/research/tool-comparison.md`](docs/research/tool-comparison.md).

---

## Runtime dependencies

`GitPython` (BSD-3-Clause) is the only required runtime dependency. The optional `web` extra
adds `Flask` (BSD-3-Clause). Their licences apply to those packages as distributed by their
own authors.
