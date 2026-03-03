"""Migration entrypoints for Inv-Man-Intake data schema."""

from inv_man_intake.data.migrations.core_schema import apply_core_schema, rollback_core_schema

__all__ = ["apply_core_schema", "rollback_core_schema"]
