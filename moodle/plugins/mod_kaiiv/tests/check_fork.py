"""Does the compatibility layer still cover the forked code?

amd/src/iv and amd/src/libcontrols came from H5P (MIT — see thirdparty/) and
they talk to a runtime that is not here. amd/src/h5pcompat.js supplies it.

The failure mode this exists for has no other warning. Nothing about a missing
H5P member is a build error: the fork is plain JavaScript reaching for a
property on an object, so a gap is `undefined`, and `undefined` is not a
problem until the line that calls it runs. That line is usually inside a
feature — opening a question, going fullscreen, reaching the end — which means
the first thing that finds the gap is a learner, part way through an activity
they cannot now finish.

It is most likely to open up when somebody takes a patch from upstream, which
is exactly the moment when everything looks fine because the diff was small.

    python moodle/plugins/mod_kaiiv/tests/check_fork.py

Run it after every upstream merge and before every release.

Not a PHPUnit test, on purpose: it checks JavaScript against JavaScript and
needs no Moodle, so making it one would mean it can only run somewhere a
database exists.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

FORKED = ["amd/src/iv", "amd/src/libcontrols"]
SHIM = "amd/src/h5pcompat.js"

# Names the fork assigns to itself rather than expecting from a runtime.
#
# Upstream this happens in src/entries/dist.js, which puts the classes on the
# global H5P once the modules have loaded. Ours are put on the shim by
# player.js at boot. They are declared in the shim as null so that this check
# can tell them apart from a name nobody thought about.
SELF_REGISTERED = {"InteractiveVideo", "InteractiveVideoInteraction"}

# Members of the shim that are ours rather than H5P's, called by player.js and
# not by the fork. Listed so the "nothing reaches for it" note stays about
# speculative code; a note that is always there is a note nobody reads.
OURS = {"reservePlayerElement"}

problems: list[str] = []
notes: list[str] = []


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def names_used() -> set[str]:
    used: set[str] = set()
    for folder in FORKED:
        base = ROOT / folder
        if not base.exists():
            problems.append(f"{folder} is missing: the fork is not vendored here")
            continue
        for path in base.rglob("*.js"):
            used |= set(re.findall(r"H5P\.([A-Za-z_][A-Za-z0-9_]*)", read(path)))
    return used


def names_provided() -> set[str]:
    path = ROOT / SHIM
    if not path.exists():
        problems.append(f"{SHIM} is missing")
        return set()
    # Top-level members of the H5P object literal. The shim is an ES module
    # (it has to be: it must assign window.H5P before the forked modules are
    # evaluated, and only import order guarantees that), so its members sit at
    # one level of indentation rather than the two an AMD wrapper would add.
    return set(re.findall(r"^    ([A-Za-z_][A-Za-z0-9_]*):", read(path), re.M))


def check_coverage() -> None:
    used = names_used()
    provided = names_provided()

    missing = used - provided
    if missing:
        problems.append(
            "the fork reaches for H5P members the shim does not have: "
            + ", ".join(sorted(missing))
            + " — add them to h5pcompat.js, or find out why the fork now "
              "needs them")

    # The shim's own rule is to provide what the fork calls and nothing else.
    # An unused member is not dangerous, it is untested: nothing exercises it,
    # so it rots quietly and then somebody relies on it.
    extra = provided - used - SELF_REGISTERED - OURS
    if extra:
        notes.append(
            "h5pcompat.js provides members nothing reaches for: "
            + ", ".join(sorted(extra))
            + " — either the fork stopped using them, or they were written "
              "speculatively. Both are reasons to delete them.")

    for name in sorted(SELF_REGISTERED):
        if name not in provided:
            problems.append(
                f"{name} is not declared in the shim. The fork registers "
                f"itself under it and reads it back; declare it as null so "
                f"the gap is visible.")


def check_self_registration_happens() -> None:
    """The null placeholders have to be filled in by somebody."""
    player = ROOT / "amd/src/player.js"
    if not player.exists():
        notes.append(
            "amd/src/player.js does not exist yet, so nothing fills in "
            + ", ".join(sorted(SELF_REGISTERED))
            + ". The player cannot run until it does.")
        return

    source = read(player)
    for name in sorted(SELF_REGISTERED):
        if not re.search(rf"\b{name}\s*=", source):
            problems.append(
                f"player.js never assigns H5P.{name}. The fork will read null "
                f"and fail at the first interaction.")


def check_licences_travel_with_it() -> None:
    """MIT costs one thing, and it costs it every time the code is shipped."""
    expected = [
        "thirdparty/LICENCE-h5p-interactive-video.md",
        "thirdparty/LICENCE-h5p-lib-controls.md",
        "thirdparty/README.md",
        "thirdparty/UPSTREAM-COMMIT.txt",
    ]
    for name in expected:
        path = ROOT / name
        if not path.exists():
            problems.append(
                f"{name} is missing. The forked code is MIT and the licence "
                f"has to ship with it; this plugin cannot be delivered "
                f"without that file.")
        elif not read(path).strip():
            problems.append(f"{name} is empty")


def check_upstream_pin_is_real() -> None:
    """A commit file that no longer names a commit is worse than none.

    The diff command in thirdparty/README.md is the whole procedure for taking
    an upstream fix. If the pin drifts, that command silently compares against
    the wrong point and the merge looks clean.
    """
    path = ROOT / "thirdparty/UPSTREAM-COMMIT.txt"
    if not path.exists():
        return

    found = re.findall(r"\b[0-9a-f]{40}\b", read(path))
    if len(found) < 2:
        problems.append(
            "thirdparty/UPSTREAM-COMMIT.txt should pin both forked "
            f"repositories to a full commit id; found {len(found)}")


def check_size_units_still_match() -> None:
    """player.js converts our percentages into the fork's em units using two
    numbers read off the fork. If an upstream patch changes either, every
    interaction is silently drawn the wrong size — the first version of the
    conversion was missing entirely, and each question covered the whole
    video with a white box that looked like a failed video load."""
    source = read(ROOT / "amd/src/iv/interactive-video.js")
    for line in ("this.fontSize = 16;", "this.width = 640;"):
        if line not in source:
            problems.append(
                f"iv/interactive-video.js no longer contains {line!r}. "
                f"FORK_WIDTH_EM in amd/src/player.js is derived from it and "
                f"has to be brought back in step.")


def check_members_of_what_the_shim_hands_out() -> None:
    """The shim gives the fork three objects: a video, a toolbar and a dialog.

    check_coverage() compares H5P.* names, and that caught none of the gaps
    that actually broke the player in a browser — getHandlerName() on the
    video, the whole dialog, $dialogContainer on the toolbar. Each was a member
    of one of these three, reached for through a variable, and each surfaced
    as "cannot read properties of undefined" at the moment a learner did the
    thing that needed it.

    So every member the fork reads off them is listed and looked for in the
    shim, as `self.<name> =`. A name the fork reaches for only through the
    editor (this.editor.dnb...) is left out: there is no editor here.
    """
    shim = read(ROOT / SHIM)
    forked = "\n".join(read(path) for folder in FORKED
                       for path in (ROOT / folder).rglob("*.js"))

    surfaces = {
        "video": r"(?<!editor\.)\b(?:this|self|that|player)\.video\.([A-Za-z_$][\w$]*)",
        "toolbar": r"(?<!editor\.)\b(?:this|self|that|player)\.dnb\.([A-Za-z_$][\w$]*)",
        "dialog": r"\bdnb\.dialog\.([A-Za-z_$][\w$]*)",
    }
    for surface, pattern in surfaces.items():
        used = set(re.findall(pattern, forked))
        # What the shim's EventDispatcher gives every one of them.
        used -= {"on", "off", "once", "trigger"}
        missing = sorted(name for name in used
                         if not re.search(r"\bself\." + re.escape(name) + r"\s*=", shim))
        if missing:
            problems.append(
                f"the fork reads these off the {surface} the shim supplies, and "
                f"the shim does not set them: {', '.join(missing)}")


def check_no_build_output_pretending_to_be_a_build() -> None:
    """mod_kaivideo's build script copies AMD sources unminified, which is a
    correct build for plain AMD. The fork is not plain AMD — it is ES modules
    with imports — so a copy produces a file the browser cannot load, and it
    fails at runtime rather than at build time."""
    build = ROOT / "amd/build"
    if not build.exists():
        notes.append("amd/build does not exist yet: nothing has been built.")
        return

    for path in build.glob("*.min.js"):
        source = read(path)
        if re.search(r"^\s*import\s", source, re.M):
            problems.append(
                f"{path.name} contains ES module syntax, so it was copied "
                f"rather than bundled. Moodle will load it as a script and "
                f"the page will fail with a syntax error.")


def main() -> int:
    print(f"fork integrity check - {ROOT.name}\n")

    check_coverage()
    check_self_registration_happens()
    check_licences_travel_with_it()
    check_upstream_pin_is_real()
    check_size_units_still_match()
    check_members_of_what_the_shim_hands_out()
    check_no_build_output_pretending_to_be_a_build()

    for note in notes:
        print(f"  note  {note}\n")

    if problems:
        print(f"{len(problems)} problem(s):\n")
        for problem in problems:
            print(f"  FAIL  {problem}\n")
        return 1

    print("  ok    the shim covers everything the fork reaches for")
    print("  ok    the licences are where they have to be")
    print()
    print("no problems" + (" (see notes above)" if notes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
