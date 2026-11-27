#!/usr/bin/env python3
"""Check or refresh the homepage's content-based asset versions."""

import argparse
import hashlib
import re
from graphlib import CycleError, TopologicalSorter
from pathlib import Path, PurePosixPath

SITE = Path(__file__).resolve().parents[1] / "release" / "marketing-homepage"
VERSIONED_ASSET = re.compile(
    rb"""(["'])(?:/|\./)([A-Za-z0-9_./-]+)\?v=([A-Za-z0-9_-]+)\1"""
)


def asset_path(match):
    path = PurePosixPath(match[2].decode("ascii"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected a path within the homepage, got {path}")
    return SITE.joinpath(*path.parts)


def refresh_versions(write):
    sources = sorted((*SITE.glob("*.html"), *SITE.glob("*.js")))
    contents = {source: source.read_bytes() for source in sources}
    references = {
        source: sorted(
            {asset_path(match) for match in VERSIONED_ASSET.finditer(content)}
        )
        for source, content in contents.items()
    }
    for paths in references.values():
        for path in paths:
            if path not in contents:
                contents[path] = path.read_bytes()

    expected = {}

    def replace(match):
        version = hashlib.sha256(contents[asset_path(match)]).hexdigest()[:12]
        start = match.start(3) - match.start()
        end = match.end(3) - match.start()
        return match[0][:start] + version.encode("ascii") + match[0][end:]

    for source in TopologicalSorter(references).static_order():
        if source in references:
            original = contents[source]
            updated = VERSIONED_ASSET.sub(replace, original)
            if original != updated:
                expected[source] = updated
            contents[source] = updated

    for source, updated in expected.items():
        if write:
            source.write_bytes(updated)
        action = "Updated" if write else "Outdated versions in"
        print(f"{action} {source.relative_to(SITE)}")
    if expected and not write:
        print(
            "Run python3 scripts/check-homepage-assets.py --write after editing assets."
        )
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Refresh versioned URLs")
    args = parser.parse_args()
    try:
        return refresh_versions(args.write)
    except (CycleError, OSError, ValueError) as error:
        parser.exit(2, f"Homepage assets: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
