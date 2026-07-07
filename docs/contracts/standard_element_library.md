# Standard Element Library Contract

This contract defines the narrow port between `inv-man-intake` and the future externally authored standard-element library. The current repository ships only a non-authoritative stub so downstream packet and operator-app work can bind to the interface without encoding human judgment.

## Data Source

The library is loaded at runtime from data. Document type identifiers and element identifiers are data values, not Python enums or application conditionals. Adding or renaming a document type must be possible by editing the library data and rerunning conformance tests.

Required root fields:

- `version`: non-empty string.
- `non_authoritative`: boolean. The bundled `_stub.json` must remain `true`.
- `doc_types`: object mapping document type id to a non-empty list of element specs.

Each element spec includes:

- `key`: stable element id, such as `operations.aum`.
- `detector_name`: name resolved through the app's detector registry.
- `mandatory`: boolean.

## Runtime Port

Consumers depend on `inv_man_intake.intake.standard_elements.StandardElementLibrary`:

- `doc_types() -> tuple[str, ...]`
- `elements_for(doc_type) -> tuple[StandardElement, ...]`
- `evaluate_coverage(doc_type, extracted) -> tuple[ElementCoverage, ...]`

The detector registry maps `detector_name` to callable detector functions. Library authors may choose regex, keyword, layout, or LLM-backed detectors later by adding registry entries; the app must not branch on element ids.

## Judgment Boundary

`classify_element_standardness()` deliberately returns only `unknown` in this repo. It is the future hook for authored standardness and red-flag deviation logic. The bundled stub must not encode claims about what is standard, acceptable, or a red flag.

## Conformance

The external library must pass `tests/intake/test_standard_element_library.py::test_conformance_against_stub` and the decoupling gate in the same file. A data-only document type addition must surface through `doc_types()` and `elements_for()` without application code changes.
