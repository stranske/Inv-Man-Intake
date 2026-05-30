#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:?usage: scripts/emit_reference_run.sh <output-dir>}"
mkdir -p "${out_dir}"

export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"

python -m inv_man_intake.cli.ingest \
  tests/fixtures/intake/pdf_primary_mixed_bundle.json \
  --out "${out_dir}"
