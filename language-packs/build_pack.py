"""Compile a pinned TEI dictionary to immutable native SQLite data, never application code.

Run on OZZZ-OS under storage-build. Signing keys stay outside the source tree.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tarfile
import unicodedata
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

NS = {"t": "http://www.tei-c.org/ns/1.0"}
TAG = "{" + NS["t"] + "}"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def normalized(value):
    return unicodedata.normalize("NFC", " ".join(value.split())).lower()


def text(node):
    return " ".join("".join(node.itertext()).split())


def valid_form(value):
    # Preserve script/accents. Function words are excluded by part of speech below.
    return (1 <= len(value) <= 128 and len(value.split()) <= 5 and any(c.isalpha() for c in value)
        and all(unicodedata.category(c)[0] in ("L", "M") or c in " '-’" for c in value))


def compile_pack(config, archive, output, signing_key, key_id):
    source = archive.read_bytes()
    if len(source) != config["source_bytes"] or hashlib.sha512(source).hexdigest() != config["source_sha512"]:
        raise ValueError("Source size/checksum mismatch")
    if output.exists():
        raise ValueError("Use a new output revision; existing pack will not be overwritten")
    output.mkdir(parents=True)
    database_path = output / "vocabulary.sqlite"
    connection = sqlite3.connect(database_path)
    connection.executescript("""
        PRAGMA application_id=1447645257;
        PRAGMA user_version=1;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE vocabulary (
            source TEXT NOT NULL, target TEXT NOT NULL, part_of_speech TEXT NOT NULL,
            PRIMARY KEY (source, target, part_of_speech)
        ) WITHOUT ROWID;
    """)
    allowed = set(config["allowed_parts_of_speech"])
    entries_seen = 0
    with tarfile.open(archive, "r:xz") as tar:
        # Read two exact, size-bounded members. Never extract archive paths to disk.
        member = tar.getmember(config["tei_member"])
        license_member = tar.getmember(config["license_member"])
        if not member.isfile() or not 0 < member.size <= 128 * 1024 * 1024:
            raise ValueError("Invalid TEI member")
        if not license_member.isfile() or not 0 < license_member.size <= 256 * 1024:
            raise ValueError("Invalid license member")
        license_text = tar.extractfile(license_member).read()
        (output / "LICENSE-data.txt").write_bytes(license_text)
        with tar.extractfile(member) as stream:
            root = None
            body = None
            license_verified = False
            for event, element in ET.iterparse(stream, events=("start", "end")):
                if event == "start":
                    if root is None: root = element
                    if element.tag == TAG + "body": body = element
                    continue
                if element.tag == TAG + "teiHeader":
                    refs = element.findall(".//t:availability//t:ref", NS)
                    license_verified = any(ref.attrib.get("target") == config["license_url"] for ref in refs)
                    if not license_verified: raise ValueError("Pinned license is not declared by source")
                    (output / "source-header.xml").write_bytes(ET.tostring(element, encoding="utf-8"))
                    element.clear()
                if element.tag != TAG + "entry": continue
                if not license_verified: raise ValueError("Dictionary has no verified license header")
                entries_seen += 1
                parts = {text(node) for node in element.findall("./t:gramGrp/t:pos", NS)} & allowed
                forms = {normalized(text(node)) for node in element.findall("./t:form/t:orth", NS)}
                targets = set()
                for citation in element.findall(".//t:cit[@type='trans']", NS):
                    if citation.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") != config["target_language"]: continue
                    targets.update(unicodedata.normalize("NFC", text(node)) for node in citation.findall("t:quote", NS))
                rows = sorted((form, target, pos) for form in forms if valid_form(form)
                    for target in targets if valid_form(target) and form != normalized(target) for pos in parts)
                connection.executemany("INSERT OR IGNORE INTO vocabulary VALUES (?, ?, ?)", rows)
                element.clear()
                if body is not None: body.remove(element)
    for key in ("pack_id", "source_language", "target_language", "revision", "source_name", "source_version", "license", "license_url", "attribution"):
        connection.execute("INSERT INTO metadata VALUES (?, ?)", (key, str(config[key])))
    connection.execute("INSERT INTO metadata VALUES ('normalization', 'unicode-nfc-lower')")
    connection.commit()
    connection.execute("VACUUM")
    count, = connection.execute("SELECT count(*) FROM vocabulary").fetchone()
    headwords, = connection.execute("SELECT count(DISTINCT source) FROM vocabulary").fetchone()
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or count == 0:
        raise ValueError("Dictionary integrity/coverage check failed")
    connection.close()
    manifest = {key: config[key] for key in ("pack_id", "source_language", "target_language", "revision", "license", "license_url", "attribution", "source_name", "source_version", "source_url", "source_sha512")}
    manifest.update(schema_version=1, normalization="unicode-nfc-lower", file="vocabulary.sqlite", bytes=database_path.stat().st_size,
        sha256=hashlib.sha256(database_path.read_bytes()).hexdigest(), entries_seen=entries_seen, headwords=headwords, mappings=count,
        compiler="vipi-tei-1", key_id=key_id, signature_algorithm="ECDSA-P256-SHA256")
    manifest_bytes = canonical(manifest)
    key = serialization.load_pem_private_key(signing_key.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("Expected a P-256 signing key")
    signature = key.sign(manifest_bytes, ec.ECDSA(hashes.SHA256()))
    key.public_key().verify(signature, manifest_bytes, ec.ECDSA(hashes.SHA256()))
    (output / "manifest.json").write_bytes(manifest_bytes)
    (output / "manifest.sig").write_bytes(signature)
    (output / "signing-public-key.der").write_bytes(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    (output / "ATTRIBUTION.txt").write_text(config["attribution"] + "\n" + config["license_url"] + "\nOriginal source: " + config["source_url"] + "\nChanges: vocabulary filtering, Unicode normalization and SQLite conversion by build_pack.py.\n", encoding="utf-8")
    print(json.dumps({"pack": config["pack_id"], "headwords": headwords, "mappings": count, "bytes": manifest["bytes"], "sha256": manifest["sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("config", "archive", "output", "signing-key"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    compile_pack(json.loads(args.config.read_text()), args.archive, args.output, args.signing_key, args.key_id)
