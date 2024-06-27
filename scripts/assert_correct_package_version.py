import sys

import click
import semver

FAIL = "\033[91m"
OKGREEN = "\033[92m"
ENDC = "\033[0m"


@click.command()
@click.option("--old-version")
@click.option("--new-version")
def assert_correct_version(old_version: str, new_version: str) -> None:
    """Asserts if new, committed semantic version is compatible with previous version, e.g. "1.0.0"."""
    old_version = old_version.replace("v", "")
    new_version = new_version.replace("v", "")
    old = semver.VersionInfo(**semver.parse(old_version))
    candidate = semver.VersionInfo(**semver.parse(new_version))

    correct_new_versions = [
        old.next_version(part) for part in ("major", "minor", "patch", "prerelease")
    ]
    if candidate not in correct_new_versions:
        sys.exit(1)
    else:
        pass


if __name__ == "__main__":
    assert_correct_version()
