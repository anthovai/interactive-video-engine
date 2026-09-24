"""Build the two files a customer installs interactive video from.

    python moodle/plugins/mod_kaiiv/tools/package.py

writes, under dist/ at the repository root:

    mod_kaiiv-<release>.zip        uploaded through Moodle's own plugin installer
    kaiiv-service-<version>.zip    the engine, built and run with Docker

Customers install these themselves, on whatever Moodle they already run. So
the plugin archive has to be exactly what Moodle's installer expects — one top
folder named after the plugin's directory, which for mod_kaiiv is "kaiiv", not
"mod_kaiiv" — and the refusal to build anything that would fail there, or
carry something it should not, happens here rather than on their server.

Refuses to build when:

  - amd/build or styles.css is older than what it is built from. The archive
    ships built output, and a customer has no node to rebuild it.
  - any of the four MIT notices is missing. The forked code may be handed on
    only with them.
"""
from __future__ import annotations

import pathlib
import re
import sys
import zipfile

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
REPO = PLUGIN.parents[2]
ENGINE = REPO / "kaiiv-service"
DIST = REPO / "dist"

# Never in a customer's copy. node_modules is the build toolchain; the reset
# script deletes a learner's records and exists for our browser tests.
PLUGIN_EXCLUDE = [
    "node_modules/",
    "tests/reset_learner.php",
    # Screenshots the browser tests leave behind when run from this folder.
    "reports/",
    "__pycache__/",
]
ENGINE_EXCLUDE = ["__pycache__/", ".pytest_cache/"]

LICENCES = [
    "thirdparty/LICENCE-h5p-interactive-video.md",
    "thirdparty/LICENCE-h5p-lib-controls.md",
    "thirdparty/README.md",
    "thirdparty/UPSTREAM-COMMIT.txt",
]

problems: list[str] = []


def excluded(relative: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/"):
            if relative.startswith(pattern) or f"/{pattern}" in f"/{relative}":
                return True
        elif relative == pattern:
            return True
    return False


def newest(paths) -> float:
    return max((p.stat().st_mtime for p in paths if p.is_file()), default=0)


def check_built_output_is_current() -> None:
    # Each built file against its own sources. backend.js is copied on its own
    # and is an external of the bundle, so a change to it leaves the bundle's
    # content — and webpack leaves an unchanged file unwritten — untouched.
    backend = PLUGIN / "amd/src/backend.js"
    bundled = [p for p in (PLUGIN / "amd/src").rglob("*.js") if p != backend]
    for built, sources in (("player.min.js", bundled), ("backend.min.js", [backend])):
        path = PLUGIN / "amd/build" / built
        if not path.exists():
            problems.append(f"amd/build/{built} is missing — run npm run build")
        elif path.stat().st_mtime + 1 < newest(sources):
            problems.append(f"amd/build/{built} is older than its source — run npm run build")

    css = PLUGIN / "styles.css"
    if not css.exists():
        problems.append("styles.css is missing — run npm run build")
    elif css.stat().st_mtime + 1 < newest((PLUGIN / "styles").glob("*.css")):
        problems.append("styles.css is older than styles/ — run npm run build")


def check_licences() -> None:
    for name in LICENCES:
        path = PLUGIN / name
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            problems.append(f"{name} is missing or empty; the forked code "
                            "cannot be handed on without it")


def plugin_release() -> tuple[str, str]:
    source = (PLUGIN / "version.php").read_text(encoding="utf-8")
    release = re.search(r"\$plugin->release\s*=\s*'([^']+)'", source).group(1)
    component = re.search(r"\$plugin->component\s*=\s*'([^']+)'", source).group(1)
    return release, component


def engine_version() -> str:
    source = (ENGINE / "app/config.py").read_text(encoding="utf-8")
    return re.search(r'SERVICE_VERSION\s*=\s*"([^"]+)"', source).group(1)


def write_zip(target: pathlib.Path, root: pathlib.Path, top: str,
              exclude: list[str]) -> int:
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if excluded(relative, exclude):
                continue
            archive.write(path, f"{top}/{relative}")
            count += 1
    return count


def main() -> int:
    check_built_output_is_current()
    check_licences()

    release, component = plugin_release()
    if component != "mod_kaiiv":
        problems.append(f"version.php names {component}, not mod_kaiiv")

    if problems:
        print("not packaged:")
        for problem in problems:
            print("  - " + problem)
        return 1

    DIST.mkdir(exist_ok=True)

    plugin_zip = DIST / f"mod_kaiiv-{release}.zip"
    # "kaiiv", not "mod_kaiiv": Moodle's installer reads the top folder as the
    # directory the plugin goes into under mod/, and refuses the upload when
    # it does not match the component.
    files = write_zip(plugin_zip, PLUGIN, "kaiiv", PLUGIN_EXCLUDE)
    print(f"wrote {plugin_zip.relative_to(REPO)}  ({files} files, "
          f"{plugin_zip.stat().st_size // 1024} KB)")

    with zipfile.ZipFile(plugin_zip) as archive:
        names = archive.namelist()
        leaked = [n for n in names if "node_modules/" in n or n.endswith("reset_learner.php")]
        if leaked:
            print("  REFUSING: archive carries " + leaked[0])
            plugin_zip.unlink()
            return 1

    engine_zip = DIST / f"kaiiv-service-{engine_version()}.zip"
    files = write_zip(engine_zip, ENGINE, "kaiiv-service", ENGINE_EXCLUDE)
    print(f"wrote {engine_zip.relative_to(REPO)}  ({files} files, "
          f"{engine_zip.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
