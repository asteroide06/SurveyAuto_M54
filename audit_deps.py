import argparse
import ast
import importlib.util
from pathlib import Path
import sys


# Correspondances utiles quand le nom d'import diffère du nom sur PyPI
IMPORT_TO_PIP = {
    "cv2": "opencv-python",
    "PIL": "pillow",
    "yaml": "pyyaml",
    "serial": "pyserial",
    "usb": "pyusb",
    "dateutil": "python-dateutil",
    "bs4": "beautifulsoup4",
}


def extract_top_level_imports(script_path: Path) -> set[str]:
    """Extrait les noms de modules de premier niveau via l'AST sans exécuter le code."""
    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(script_path))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0].strip()
                if root:
                    imports.add(root)
        elif isinstance(node, ast.ImportFrom):
            # level == 0 exclut les imports relatifs (ex. : from .helper import foo)
            if node.level == 0 and node.module:
                root = node.module.split(".")[0].strip()
                if root:
                    imports.add(root)

    return imports


def collect_local_names(targets: list[Path]) -> set[str]:
    """Répertorie les noms de modules/dossiers locaux autour des fichiers analysés."""
    local_names: set[str] = set()
    search_dirs: set[Path] = set()

    for t in targets:
        if t.is_dir():
            search_dirs.add(t.resolve())
            for py_file in t.rglob("*.py"):
                local_names.add(py_file.stem)
        elif t.is_file():
            search_dirs.add(t.parent.resolve())
            local_names.add(t.stem)

    for folder in search_dirs:
        local_names.add(folder.name)
        for child in folder.iterdir():
            if child.is_dir():
                local_names.add(child.name)
            elif child.suffix == ".py":
                local_names.add(child.stem)

    return local_names


def resolve_python_files(raw_paths: list[str]) -> list[Path]:
    """Résout une liste de fichiers .py ou de dossiers en liste triée de fichiers .py."""
    files: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if not p.exists():
            print(f"[AVERTISSEMENT] Chemin introuvable : {p}", file=sys.stderr)
            continue
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.suffix == ".py":
            files.append(p)
        else:
            print(f"[AVERTISSEMENT] Ignoré (pas un .py ou dossier) : {p}", file=sys.stderr)

    # Déduplication tout en conservant l'ordre
    unique_files: list[Path] = []
    seen: set[Path] = set()
    for f in files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(f)
    return unique_files


def is_module_available(module_name: str) -> bool:
    """Vérifie si un module est trouvable dans l'environnement courant sans exécuter son code."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError, ImportError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audite les dépendances d'un ou plusieurs scripts Python sans les exécuter."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Un ou plusieurs fichiers .py ou dossiers à analyser",
    )
    args = parser.parse_args()

    raw_targets = [Path(p) for p in args.paths if Path(p).exists()]
    py_files = resolve_python_files(args.paths)

    if not py_files:
        print("Aucun fichier .py valide à analyser.", file=sys.stderr)
        return 2

    stdlib_modules = getattr(sys, "stdlib_module_names", set())
    local_names = collect_local_names(raw_targets)

    all_missing_modules: set[str] = set()
    per_file_missing: dict[Path, list[str]] = {}

    for py_file in py_files:
        try:
            imported = extract_top_level_imports(py_file)
        except SyntaxError as exc:
            print(f"[ERREUR SYNTAXE] {py_file} : {exc}", file=sys.stderr)
            continue

        missing_for_file: list[str] = []
        for mod in sorted(imported):
            if mod in stdlib_modules or mod in local_names:
                continue
            if not is_module_available(mod):
                missing_for_file.append(mod)
                all_missing_modules.add(mod)

        if missing_for_file:
            per_file_missing[py_file] = missing_for_file

    print(f"Interpréteur vérifié : {sys.executable}")
    print(f"Fichiers analysés     : {len(py_files)}")

    if not per_file_missing:
        print("Résultat : toutes les dépendances détectées sont présentes.")
        return 0

    print("\nModules manquants par fichier :")
    for py_file, mods in per_file_missing.items():
        print(f"  - {py_file} : {', '.join(mods)}")

    pip_suggestions = sorted(
        {IMPORT_TO_PIP.get(mod, mod) for mod in all_missing_modules}
    )
    print("\nModules externes manquants (global) :")
    print(" ", ", ".join(sorted(all_missing_modules)))
    print("\nCommande d'installation suggérée (à vérifier selon vos paquets exacts) :")
    print(f"  {sys.executable} -m pip install {' '.join(pip_suggestions)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())