"""Run Qt test modules in separate processes from the repository root."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent.parent
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    failures = []
    modules = sorted((root / "tests").glob("test_*.py"))
    if not modules:
        print("Aucun module de tests trouvé.", file=sys.stderr)
        return 1
    for module in modules:
        print(f"\n{module.name}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", module.name, "-v"],
            cwd=root, env=environment,
        )
        if result.returncode:
            failures.append(module.name)
    if failures:
        print("\nModules en échec : " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"\nTous les modules ont réussi ({len(modules)} modules).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
