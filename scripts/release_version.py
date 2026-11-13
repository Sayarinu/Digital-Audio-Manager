#!/usr/bin/env python3
"""Choose Stable/Experimental versions using Tubify's branch and PR-label rules.

Stable merges bump by Major Release / Feature / patch; experimental builds count
X.Y.ZbN towards that stable version. Stamp only the bundled runtime version.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
VERSION_LINE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.M)
STABLE_BRANCH, EXPERIMENTAL_BRANCH = "refs/heads/main", "refs/heads/experimental"
# Label names are matched case-insensitively; the release:* names are accepted from older PRs.
LEVELS = {"major release": 3, "feature": 2, "release:major": 3, "release:feature": 2, "release:minor": 2}
PATCH, MINOR, MAJOR = 1, 2, 3
NAMES = {PATCH: "patch", MINOR: "feature", MAJOR: "major"}


def declared():
    match = VERSION_LINE.search(PYPROJECT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("pyproject.toml has no MAJOR.MINOR.PATCH version")
    return tuple(int(part) for part in match.groups())


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def load_updates():
    """The app's own tag and version rules (standard library only)."""
    spec = importlib.util.spec_from_file_location("dam_updates", ROOT / "native/src/dam/updates/updates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updates = load_updates()


def release_tags(*args):
    """(version key, tag) for every release tag in either format, newest last."""
    return sorted((updates.version_key(name), name) for name in git("tag", "--list", *args).split() if updates.tag_version(name))


def previous_tag(ref="HEAD"):
    """The newest stable release already contained in ``ref``."""
    tags = [row for row in release_tags("--merged", ref) if row[0][3] == 1]
    return tags[-1][1] if tags else None


def newest_stable_tag():
    """The newest stable release anywhere in the repository, merged or not, as ((X, Y, Z), tag)."""
    tags = [row for row in release_tags() if row[0][3] == 1]
    return (tags[-1][0][:3], tags[-1][1]) if tags else None


def experimental_builds(version):
    """Build numbers already released for the experimental series of ``version``."""
    return [key[4] for key, _name in release_tags() if key[3] == 0 and key[:3] == tuple(version)]


def previous_experimental(ref="HEAD"):
    """The newest experimental build already contained in ``ref``."""
    tags = [row for row in release_tags("--merged", ref) if row[0][3] == 0]
    return tags[-1][1] if tags else None


def experimental_version(floor, labels):
    newest = newest_stable_tag()
    base = newest[0] if newest else floor
    # Only changes that have not reached a stable release yet decide where experimental is heading.
    commits = git("rev-list", "--no-merges", "--max-count=200", "origin/main..HEAD").split()
    level = release_level(commits, labels)
    target = next_version(base, level, floor)
    build = max(experimental_builds(target), default=0) + 1
    return f"{text(target)}b{build}", NAMES[level], previous_experimental() or "origin/main"


def bump(version, level):
    major, minor, patch = version
    if level >= MAJOR:
        return (major + 1, 0, 0)
    if level >= MINOR:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def github_pulls(repository, token):
    """Return a function giving the pull requests (title, number, labels) that merged a commit."""
    def pulls(sha):
        request = Request(f"https://api.github.com/repos/{repository}/commits/{sha}/pulls",
                          headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "dam-release"})
        with urlopen(request, timeout=20) as response:
            return [pull for pull in json.load(response) if pull.get("merged_at")]
    return pulls


def github_labels(repository, token):
    """Return a function giving the labels of the PRs that merged a commit."""
    pulls = github_pulls(repository, token)
    return lambda sha: {label["name"] for pull in pulls(sha) for label in pull.get("labels", [])}


def release_level(commits, labels):
    level = PATCH
    for sha in commits:
        level = max([level] + [LEVELS[name.casefold()] for name in labels(sha) if name.casefold() in LEVELS])
    return level


def next_version(base, level, floor):
    return max(bump(base, level), floor)


def text(version):
    return ".".join(map(str, version))


def release_version(environ=os.environ, labels=None):
    """Return (version, level name, previous tag) for this CI event."""
    floor = declared()
    ref, event = environ.get("GITHUB_REF", ""), environ.get("GITHUB_EVENT_NAME", "")
    if ref.startswith("refs/tags/") and updates.tag_version(ref.removeprefix("refs/tags/")):
        return updates.tag_version(ref.removeprefix("refs/tags/")), "tag", ""
    if not (event == "push" and ref in {STABLE_BRANCH, EXPERIMENTAL_BRANCH}):
        return text(floor), "none", ""
    if labels is None:
        labels = github_labels(environ["GITHUB_REPOSITORY"], environ["GH_TOKEN"])
    if ref == EXPERIMENTAL_BRANCH:
        return experimental_version(floor, labels)
    previous = previous_tag()
    # Every change merged since the last release decides how big this one is.
    commits = git("rev-list", "--no-merges", "--max-count=200", f"{previous}..HEAD").split() if previous else git("rev-list", "-1", "HEAD").split()
    level = release_level(commits, labels)
    base = updates.version_key(previous)[:3] if previous else floor
    return text(next_version(base, level, floor)), NAMES[level], previous or ""


def is_release(environ):
    """Pushes to main or experimental, and release tags, publish signed releases."""
    ref = environ.get("GITHUB_REF", "")
    return (ref.startswith("refs/tags/") and bool(updates.tag_version(ref.removeprefix("refs/tags/")))) or (environ.get("GITHUB_EVENT_NAME") == "push" and ref in {STABLE_BRANCH, EXPERIMENTAL_BRANCH})


def stamp(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:b\d+)?", version):
        raise SystemExit("Invalid release version: " + version)
    (ROOT / "native/src/dam/assets/build-version.txt").write_text(version + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Choose or stamp the native release version.")
    parser.add_argument("--stamp", metavar="VERSION", help="write VERSION into the runtime build stamp")
    args = parser.parse_args(argv)
    if args.stamp:
        stamp(args.stamp)
        print(args.stamp)
        return 0
    version, level, previous = release_version()
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={version}\nlevel={level}\nprevious={previous}\n")
            handle.write(f"prerelease={'true' if 'b' in version else 'false'}\n")
            newest = newest_stable_tag()
            handle.write(f"stable={text(newest[0]) if newest else ''}\n")
            handle.write(f"tag={updates.release_tag(version)}\n")
            handle.write(f"publish={'true' if is_release(os.environ) else 'false'}\n")
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
