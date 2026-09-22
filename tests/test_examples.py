"""The examples compile and only use public names."""

import ast
import pathlib

import levanto

EXAMPLES = sorted((pathlib.Path(__file__).parent.parent / "examples").glob("*.py"))


def test_examples_exist():
    assert EXAMPLES


def test_examples_import_only_public_names():
    for path in EXAMPLES:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "levanto":
                for alias in node.names:
                    assert alias.name in levanto.__all__, f"{path.name}: {alias.name} is not exported"
