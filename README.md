# Falsifier

Falsifier checks model-proposed code patches by running them in isolated sandboxes, and keeps only the findings that execution supports.

## Problem

_TODO: describe the problem Falsifier addresses._

## How it works

_TODO: describe the red, patch, green loop and how evidence is collected._

## Verdicts

_TODO: list the possible verdicts and what each one means._

## Usage

_TODO: installation and CLI usage._

## Limitations

_TODO: known limitations._

## Prior art

    Falsifier is an independent implementation. Three projects shaped the design:
    - PatchProof (Apache-2.0) for the red, patch, green loop and per-attempt evidence
    - Kelp (MIT) for evidence-gated findings: the model proposes, execution decides
    - CodeMore (MIT) for pairing every rule with true-positive and false-positive fixtures
    No code was copied from any of them.
