from __future__ import annotations

import re
from pathlib import Path
import tempfile
import unittest

from ggen_create.package import build_package
from ggen_create.session import add_paths, set_seed, start_session


def fixture_session(root: Path, name: str) -> Path:
    (root / "Hello.txt").write_text("Hello hello HELLO", encoding="utf-8")
    session = start_session(root, name)
    add_paths(session, ["Hello.txt"], cwd=root)
    set_seed(session, "Hello")
    return session


def _subject_iri(ontology_text: str) -> str:
    match = re.search(r"gc:(subject\S*)\s+a\s+gc:GenerationSubject", ontology_text)
    assert match is not None, ontology_text
    return match.group(1)


def _query_text(package: Path) -> str:
    tmpl_files = sorted((package / "templates").glob("*.tmpl"))
    assert tmpl_files
    return tmpl_files[0].read_text(encoding="utf-8")


class PackageSubjectCollisionTests(unittest.TestCase):
    def test_two_generators_mint_distinct_subject_iris_and_do_not_cross_join(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            packages_dir = root / "packages"

            alpha_root = root / "alpha_src"
            alpha_root.mkdir()
            alpha_session = fixture_session(alpha_root, "alpha")
            alpha_package = build_package(alpha_session, packages_dir).package_dir

            beta_root = root / "beta_src"
            beta_root.mkdir()
            beta_session = fixture_session(beta_root, "beta")
            beta_package = build_package(beta_session, packages_dir).package_dir

            alpha_ontology = (alpha_package / "ontology.ttl").read_text(
                encoding="utf-8"
            )
            beta_ontology = (beta_package / "ontology.ttl").read_text(
                encoding="utf-8"
            )

            alpha_iri = _subject_iri(alpha_ontology)
            beta_iri = _subject_iri(beta_ontology)

            # 1. Distinct minted subject IRIs per generator.
            self.assertNotEqual(alpha_iri, beta_iri)

            # 2. Each package's SPARQL query references its own minted IRI,
            # consistently with its own ontology.
            alpha_query = _query_text(alpha_package)
            beta_query = _query_text(beta_package)
            self.assertIn(f"gc:{alpha_iri}", alpha_query)
            self.assertIn(f"gc:{beta_iri}", beta_query)
            self.assertNotIn(f"gc:{beta_iri}", alpha_query)
            self.assertNotIn(f"gc:{alpha_iri}", beta_query)

            # 3. Construct the union of both real ontology.ttl files, the way
            # a real ggen consumer merges RDF from two packs pulled together.
            combined_ontology = alpha_ontology + "\n" + beta_ontology

            # Each package's own minted IRI, as a literal substring, appears
            # only among that package's own facts in the combined graph --
            # i.e. it does not appear anywhere in the OTHER package's block.
            self.assertNotIn(f"gc:{alpha_iri}", beta_ontology)
            self.assertNotIn(f"gc:{beta_iri}", alpha_ontology)

            # And each package's query, run "against" the combined graph,
            # only has facts under its own subject IRI available to bind --
            # confirm the combined graph contains exactly one declaration of
            # each subject (not merged/collided into a shared one).
            self.assertEqual(
                combined_ontology.count(
                    f"gc:{alpha_iri} a gc:GenerationSubject"
                ),
                1,
            )
            self.assertEqual(
                combined_ontology.count(f"gc:{beta_iri} a gc:GenerationSubject"),
                1,
            )


if __name__ == "__main__":
    unittest.main()
