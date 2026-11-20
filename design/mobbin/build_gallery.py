"""Build Vipi's local feature gallery from the catalog and private screen originals."""
import argparse
import hashlib
import json
from collections import Counter
from html import escape
from pathlib import Path


def local_file(directory, relative):
    path = directory / relative
    if path.resolve().is_relative_to(directory) and path.is_file():
        return escape(relative, quote=True)
    raise ValueError(f"Missing file in the private library: {relative}")


def link(url, label):
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def render(catalog, directory):
    screens, flows, journeys = (catalog[key] for key in ("screens", "flows", "journeys"))
    for screen in screens.values():
        local_file(directory, screen["file"])
        local_file(directory, screen["thumbnail"])
        digest = hashlib.sha256((directory / screen["file"]).read_bytes()).hexdigest()
        if digest != screen["sha256"]:
            raise ValueError(f'Image differs from catalog: {screen["file"]}')

    examples = directory / "vipi/examples.json"
    native = json.loads(examples.read_text()) if examples.exists() else {}
    titles = {journey["title"] for journey in journeys}
    for title, items in native.items():
        if title not in titles:
            raise ValueError(f"Unknown feature for native evidence: {title}")
        for item in items:
            local_file(directory, item["file"])

    sections = []
    for journey in journeys:
        cards = []
        for uid in journey["screens"]:
            screen = screens[uid]
            app, platform = escape(screen["app"]), escape(screen["platform"])
            cards.append(
                f'<figure><a href="{escape(screen["file"])}" aria-label="Open full-size {app} screen">'
                f'<img loading="lazy" src="{escape(screen["thumbnail"])}" alt="{app} {platform} screen"></a>'
                f'<figcaption>{link(screen["url"], screen["app"])} · {platform}</figcaption></figure>'
            )
        references = [link(flows[uid]["url"], flows[uid]["app"] + " · " + flows[uid]["name"])
                      for uid in journey["flows"]]
        captures = [link(item["file"], item["label"]) for item in native.get(journey["title"], [])]
        section_id = "".join(char if char.isalnum() else "-" for char in journey["title"].lower()).strip("-")
        sections.append(
            f'<section data-area="{escape(journey["area"])}" id="{section_id}">'
            f'<small>{escape(journey["area"])}</small><h2>{escape(journey["title"])}</h2>'
            f'<p>{escape(journey["note"])}</p><p>{" · ".join(references)}</p>'
            f'<p class="native">{" · ".join(captures)}</p><div class="refs">{"".join(cards)}</div></section>'
        )

    areas = dict.fromkeys(journey["area"] for journey in journeys)
    options = "".join(f"<option>{escape(area)}</option>" for area in areas)
    platform_counts = Counter(screen["platform"] for screen in screens.values())
    platforms = ", ".join(f"{count} {platform}" for platform, count in platform_counts.items())
    overview = (f"{len(journeys)} features · {len(screens)} original screens ({platforms}) · "
                f"{len(flows)} complete flows")
    html = Path(__file__).with_name("gallery.html").read_text()
    for token, value in {
        "@SUMMARY@": overview, "@COLLECTION@": escape(catalog["collection"], quote=True),
        "@AREAS@": options, "@FEATURES@": "".join(sections),
    }.items():
        html = html.replace(token, value)
    return html


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path, help="Directory containing private screens/ and previews/")
    directory = parser.parse_args().library.resolve(strict=True)
    source = Path(__file__).with_name("catalog.json")
    data = source.read_bytes()
    html = render(json.loads(data), directory)
    (directory / "catalog.json").write_bytes(data)
    (directory / "index.html").write_text(html)
