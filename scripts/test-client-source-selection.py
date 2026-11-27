#!/usr/bin/env python3
"""Check that source publication includes build inputs without retired catalogs."""

import pathlib
import runpy
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/prepare-client-source.py"))
READINGS = runpy.run_path(str(ROOT / "scripts/check-client-reading-data.py"))


class SourceSelectionTest(unittest.TestCase):
    def test_retired_data_and_private_material_are_not_selected(self):
        selected = MODULE["selected_source"]
        for path in (
            "data/immersion/all-pair-source-catalog-001.json",
            "data/lexical/catalog.json",
            "data/lexical/en-es.sqlite.zlib",
            "data/examples/sentence-readings.json",
            "language-packs/accepted-local-source-003/manifest.json",
            "language-packs/expansion-starter-20261117-r02/packs/source.json",
            "backend/vipi/config.py",
            "release/receipt.json",
            ".git/config",
            "android/BUILDING.md",
            "ios/BUILDING.md",
            "android/app/src/androidTest/java/co/fallsoft/vipi/ProfileSnapshotCompareDeviceTest.kt",
            "qa/immersion/chinese-reading-upstream-r01/private-note.json",
        ):
            self.assertFalse(selected(path), path)

    def test_real_tree_keeps_readings_and_native_build_inputs(self):
        names = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT, text=True
        ).splitlines()
        selected = {name for name in names if MODULE["selected_source"](name)}
        for path in (
            "android/app/build.gradle.kts",
            "ios/project.yml",
            "ios/Podfile.lock",
            "data/readings/chinese-ordinary.json",
            "data/readings/chinese-reviewed-words.json",
            "language-packs/export_marked_chinese_readings.mjs",
            "qa/immersion/chinese-reading-upstream-r01/pinyin-pro-3.29.5.tgz",
            "qa/immersion/chinese-reading-upstream-r01/LICENSE.upstream",
            "qa/backup/android-history-v1.vipihistory",
            "qa/immersion/speech.json",
            "scripts/build-android.sh",
            "scripts/prepare-ios-project.sh",
            "vendor/cld2/NOTICE",
        ):
            self.assertIn(path, selected)
        self.assertFalse(
            any(
                name.startswith(("data/immersion/", "data/lexical/", "data/examples/"))
                for name in selected
            )
        )
        for name in selected:
            if name.startswith("language-packs/"):
                self.assertEqual(
                    name, "language-packs/export_marked_chinese_readings.mjs"
                )

    def test_runtime_readings_verify_without_any_translation_catalog(self):
        directory = ROOT / "data/readings"
        expected = READINGS["verify"](directory)
        with tempfile.TemporaryDirectory(
            prefix="vipi-reading-source-", dir=ROOT / "qa"
        ) as temporary:
            isolated = pathlib.Path(temporary)
            for name in ("chinese-ordinary.json", "chinese-ordinary.provenance.json"):
                (isolated / name).write_bytes((directory / name).read_bytes())
            self.assertEqual(READINGS["verify"](isolated), expected)
            raw = (isolated / "chinese-ordinary.json").read_bytes()
            (isolated / "chinese-ordinary.json").write_bytes(b" " + raw[1:])
            self.assertEqual(
                len(raw), (isolated / "chinese-ordinary.json").stat().st_size
            )
            with self.assertRaisesRegex(ValueError, "differs"):
                READINGS["verify"](isolated)

    def test_export_path_safety_and_prefix_boundaries(self):
        for name in ("/private/key", "../key", "data/../key", "data\\key"):
            with self.assertRaises(ValueError):
                MODULE["safe_name"](name)
        self.assertFalse(MODULE["selected_source"]("android-private/key"))
        self.assertFalse(MODULE["selected_source"]("data/readings-private/key"))

    def test_old_release_cannot_be_exported_without_its_required_catalogs(self):
        old_inputs = [
            subprocess.check_output(
                ["git", "show", "55a9f723f436f4252730c0a85358a9aa32080f8b:" + name],
                cwd=ROOT,
                text=True,
            )
            for name in ("android/app/build.gradle.kts", "ios/project.yml")
        ]
        with self.assertRaisesRegex(ValueError, "retired translation resources"):
            MODULE["verify_provider_build_inputs"](*old_inputs)


if __name__ == "__main__":
    unittest.main()
