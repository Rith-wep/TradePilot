import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "tradepilot"
DOMAIN_PACKAGES = {
    "accounting",
    "backtesting",
    "core",
    "data",
    "indicators",
    "reporting",
    "strategies",
    "validation",
}
DATA_HIGHER_LAYERS = {
    "indicators",
    "reporting",
    "strategies",
    "validation",
}
COMPATIBILITY_SHIMS = {
    Path("data/readiness_pipeline.py"),
}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.lineno, node.module
        elif isinstance(node, ast.Import):
            for name in node.names:
                yield node.lineno, name.name


def _is_cli_adapter(path: Path) -> bool:
    return path.name == "cli.py" or path.name.endswith("_cli.py")


class DependencyBoundaryTests(unittest.TestCase):
    def test_domain_modules_do_not_import_workflows_or_cli_adapters(self):
        violations = []
        for path in PACKAGE_ROOT.rglob("*.py"):
            relative = path.relative_to(PACKAGE_ROOT)
            if relative.parts[0] not in DOMAIN_PACKAGES or _is_cli_adapter(path):
                continue
            for line, imported in _imports(path):
                if ".cli" in imported or imported.endswith("_cli"):
                    violations.append(f"{relative}:{line} imports CLI module {imported}")
                if (
                    imported.startswith("tradepilot.workflows")
                    and relative not in COMPATIBILITY_SHIMS
                ):
                    violations.append(f"{relative}:{line} imports workflow {imported}")
        self.assertEqual(violations, [])

    def test_data_domain_does_not_import_higher_research_layers(self):
        violations = []
        for path in (PACKAGE_ROOT / "data").rglob("*.py"):
            relative = path.relative_to(PACKAGE_ROOT)
            if _is_cli_adapter(path) or relative in COMPATIBILITY_SHIMS:
                continue
            for line, imported in _imports(path):
                if not imported.startswith("tradepilot."):
                    continue
                target = imported.split(".")[1]
                if target in DATA_HIGHER_LAYERS:
                    violations.append(f"{relative}:{line} imports {imported}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
