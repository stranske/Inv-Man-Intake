#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:?usage: scripts/emit_reference_run.sh <output-dir>}"
mkdir -p "${out_dir}"

export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"

staging_dir="$(mktemp -d)"
trap 'rm -rf "${staging_dir}"' EXIT

bundle_src="tests/fixtures/intake/pdf_primary_mixed_bundle.json"
extraction_root="tests/fixtures/extraction"
needed_files=(
  summit_arc_investment_update.pdf
  summit_arc_track_record.xlsx
)

for file_name in "${needed_files[@]}"; do
  cp "${extraction_root}/${file_name}" "${staging_dir}/${file_name}"
done

python - "${bundle_src}" "${staging_dir}/reference_bundle.json" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
payload = json.loads(source.read_text(encoding="utf-8"))
allowed = {
    "summit_arc_investment_update.pdf",
    "summit_arc_track_record.xlsx",
}
payload["files"] = [
    entry
    for entry in payload["files"]
    if isinstance(entry, dict) and entry.get("file_name") in allowed
]
target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

python -m inv_man_intake.cli.ingest \
  "${staging_dir}/reference_bundle.json" \
  --out "${out_dir}"
