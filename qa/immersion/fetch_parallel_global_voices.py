#!/usr/bin/env python3
"""Pin public PGV parallel archives for all Vipi languages; never promote mappings."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import zipfile

BASE = "https://nlp.ilsp.gr/pgv/"
LANGUAGES = dict(ara="ar", deu="de", eng="en", spa="es", fra="fr", ita="it",
                 jpn="ja", kor="ko", por="pt", swa="sw", zhs="zh")


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    with urlopen(BASE, timeout=30) as response:
        index = response.read(2_000_001)
    assert len(index) <= 2_000_000
    (args.output / "source-index.html").write_bytes(index)
    links = {}
    for href in re.findall(r'''href=["']([^"']+)["']''', index.decode(), re.I):
        match = re.search(r"/([a-z]{3})-([a-z]{3})[.]zip$", href)
        if match and set(match.groups()) <= LANGUAGES.keys():
            links["-".join(match.groups())] = urljoin(BASE, href)
    assert len(links) == 55, "The source matrix changed; inspect before acquiring a different corpus"

    def inspect(item):
        pair, url = item
        assert url.startswith(BASE + "archives/")
        with urlopen(Request(url, method="HEAD"), timeout=30) as response:
            size = int(response.headers["Content-Length"])
        assert 0 < size <= args.max_bytes
        return dict(pair=pair, url=url, bytes=size)

    with ThreadPoolExecutor(max_workers=4) as workers:
        planned = list(workers.map(inspect, sorted(links.items())))
    assert sum(row["bytes"] for row in planned) + len(index) < args.max_bytes
    plan = dict(schema="vipi-pgv-acquisition-1", source_url=BASE,
                source_index_sha256=hashlib.sha256(index).hexdigest(),
                languages=LANGUAGES, archives=planned, complete=False,
                release_ready=False, license="CC-BY-4.0",
                license_scope="PGV alignment distribution; original Global Voices content retains its attribution license",
                citation="Prokopis Prokopidis, Vassilis Papavassiliou and Stelios Piperidis. 2016. Parallel Global Voices: a collection of multilingual corpora with citizen media stories. LREC 2016.",
                alignment="Automatic segment alignment of directly linked translated documents; not independently verified sentence translations",
                algorithm_sources="Index page says hunalign; archive README and TMX header identify mALIGNa. Retain original artifacts rather than infer equivalence.")
    receipt = args.output / "receipt.json"
    receipt.write_text(json.dumps(plan, indent=2) + "\n")

    def download(row):
        path = args.output / (row["pair"] + ".zip")
        partial = path.with_suffix(".zip.partial")
        digest = hashlib.sha256()
        total = 0
        with urlopen(row["url"], timeout=60) as response, partial.open("xb") as stream:
            while chunk := response.read(1 << 20):
                total += len(chunk)
                assert total <= row["bytes"], "Upstream archive changed after size admission"
                digest.update(chunk)
                stream.write(chunk)
        assert total == row["bytes"]
        with zipfile.ZipFile(partial) as archive:
            members = [dict(name=v.filename, bytes=v.file_size, compressed_bytes=v.compress_size)
                       for v in archive.infolist()]
            assert members and all(v["bytes"] <= 5_000_000_000 for v in members)
        partial.rename(path)
        return dict(row, sha256=digest.hexdigest(), members=members)

    with ThreadPoolExecutor(max_workers=4) as workers:
        archives = list(workers.map(download, planned))
    plan.update(archives=archives, complete=True,
                compressed_bytes=sum(v["bytes"] for v in archives),
                uncompressed_bytes=sum(m["bytes"] for v in archives for m in v["members"]),
                seconds=round(time.monotonic()-started, 3))
    receipt.write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({k:plan[k] for k in ("complete", "compressed_bytes", "uncompressed_bytes", "seconds")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=500_000_000)
    main(parser.parse_args())
