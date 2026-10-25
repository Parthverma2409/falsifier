# Falsifier

Falsifier checks model-proposed code patches by running them in isolated sandboxes, and keeps only the findings that execution supports.

## Problem

_TODO: describe the problem Falsifier addresses._

## How it works

_TODO: describe the red, patch, green loop and how evidence is collected._

**"Benchmark oracle" means the repository's own FAIL_TO_PASS tests**, as listed in SWE-bench
Verified. It does not mean a reproduction of SWE-bench's harness, which Falsifier does not
reimplement. The "SWE-bench says" column is the dataset's published label (`falsifier/official.py`).

## Verdicts

_TODO: list the possible verdicts and what each one means._

## Usage

_TODO: installation and CLI usage._

### Configuration

Settings live in `falsifier/config.py`; this list mirrors it.

| Setting | Value | Override |
|---|---|---|
| Token Factory base_url (OpenAI-compatible) | `https://api.tokenfactory.nebius.com/v1/` | `FALSIFIER_BASE_URL` |
| Generation model | `nvidia/Nemotron-3_5-Lightning`, thinking off | `FALSIFIER_MODEL` |
| Model price, USD per 1M tokens in / out | 0.06 / 0.24 | `FALSIFIER_USD_PER_M_INPUT`, `FALSIFIER_USD_PER_M_OUTPUT` |
| Response cache (gitignored) | `.cache/generate/` | `FALSIFIER_GENERATE_CACHE` |
| Sandbox spend ceiling | set per script | `FALSIFIER_SPEND_CEILING_USD` |

`NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID` are read from the environment or a local `.env`; see
`.env.example`.

## Limitations

This section names real holes, as they are found. The full list is written after the run.

- **Equivalence is relative to the input domain, not absolute.** Falsifier discards a surviving
  mutant as equivalent when its own witness cannot tell it apart from the patch. That discard is
  sound only within the domain the witness explores. A mutant equivalent over one domain can be
  distinguishable over a wider one. `clamp` with `x > hi - 1` is the same as the patch for
  integers and different for `clamp(9.5, 0, 10)`. If the code accepts more than its witness
  tries, a discarded mutant may be a real survivor, and EARNED may be too generous.
  The fixtures `earned_clamp` (integers only, enforced) and `unearned_clamp_float` (floats
  accepted, integer-only test) pin both sides. We found this when our own oracle contradicted
  our own fixture: the fixture said `killed`, the oracle said `equivalent`, and the oracle was
  right.

## Prior art

Falsifier is an independent implementation. Three projects shaped the design:

- PatchProof (Apache-2.0) for the red, patch, green loop and per-attempt evidence
- Kelp (MIT) for evidence-gated findings: the model proposes, execution decides
- CodeMore (MIT) for pairing every rule with true-positive and false-positive fixtures

No code was copied from any of them.

## License

MIT. See [LICENSE](LICENSE).
