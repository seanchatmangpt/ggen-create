"""Public facade for the bounded ggen-create -> ggen-legacy intake rail."""

from .legacy_bundle import build_legacy_bundle, verify_legacy_bundle
from .legacy_model import LegacyBuildResult, plan_legacy_factory, receiving_contract, render_ontology

__all__ = [
    "LegacyBuildResult",
    "build_legacy_bundle",
    "plan_legacy_factory",
    "receiving_contract",
    "render_ontology",
    "verify_legacy_bundle",
]
