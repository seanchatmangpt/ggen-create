"""Shared fixtures for Chicago-school JTBD acceptance tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

CLI = [sys.executable, "-m", "ggen_create"]


class CliOutcome:
    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.completed = completed
        self.exit_code = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    def refused(self, code: str) -> bool:
        return code in self.stderr


def run_create(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
    json_output: bool = False,
) -> CliOutcome:
    command = [*CLI]
    if json_output:
        command.append("--json")
    command.extend(args)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})},
    )
    return CliOutcome(completed)


def write_greeter_exemplar(root: Path) -> None:
    (root / "dist").mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "hello",
                "version": "1.0.0",
                "scripts": {"hello": "node dist/hello.js"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "dist/hello.js").write_text(
        'console.log("Hello!")\n',
        encoding="utf-8",
    )


def capture_greeter_via_cli(root: Path, seed: str = "Hello") -> Path:
    outcome = run_create(root, "start", "greeter", json_output=True)
    if outcome.exit_code != 0:
        raise AssertionError(outcome.stderr)
    session = Path(outcome.json["session"])
    for command, args in (
        ("add", ("package.json", "dist/hello.js")),
        ("usename", (seed,)),
    ):
        step = run_create(root, command, *args, json_output=True)
        if step.exit_code != 0:
            raise AssertionError(step.stderr)
    return session


def write_bounded_fake_ggen(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
from pathlib import Path
from ggen_create.cases import values_for

root = Path.cwd()
meta = json.loads((root / "ggen-create-package.json").read_text())
value = meta["parameter"]["value"]
values = values_for(value)

def render(text):
    for key, replacement in values.items():
        text = text.replace("{{ row." + key + " }}", replacement)
    return text.replace("{% raw %}", "").replace("{% endraw %}", "")

for item in meta["files"]:
    template = (root / item["template"]).read_text()
    parts = template.split("---" + "\\n", 2)
    if len(parts) != 3:
        raise SystemExit("invalid template: " + item["template"])
    target = root / render(item["target"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(parts[2]))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def hola_reference_tree(root: Path, session_path: Path) -> Path:
    reference = root / "reference"
    (reference / "dist").mkdir(parents=True)
    (reference / "package.json").write_text(
        json.dumps(
            {
                "name": "hola",
                "version": "1.0.0",
                "scripts": {"hola": "node dist/hola.js"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (reference / "dist/hola.js").write_text(
        'console.log("Hola!")\n',
        encoding="utf-8",
    )
    generated_session = json.loads(session_path.read_text(encoding="utf-8"))
    generated_session["hygen_create_version"] = "0.2.1"
    generated_session["templatize_using_name"] = "Hola"
    generated_session["files_and_dirs"] = {
        (
            "hygen-create.json"
            if key == "ggen-create.json"
            else "dist/hola.js"
            if key == "dist/hello.js"
            else key
        ): included
        for key, included in generated_session["files_and_dirs"].items()
    }
    (reference / "hygen-create.json").write_text(
        json.dumps(generated_session, indent=2) + "\n",
        encoding="utf-8",
    )
    return reference


class GreeterWorkspace:
    """Temporary greeter exemplar with CLI-captured session."""

    def __init__(self) -> None:
        self._holder = tempfile.TemporaryDirectory()
        self.root = Path(self._holder.name)
        write_greeter_exemplar(self.root)
        self.session = capture_greeter_via_cli(self.root)

    def close(self) -> None:
        self._holder.cleanup()

    def __enter__(self) -> GreeterWorkspace:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def run(self, *args: str, json_output: bool = False) -> CliOutcome:
        return run_create(self.root, *args, json_output=json_output)

    def package_root(self) -> Path:
        return self.root / "packages"
