#!/usr/bin/env python3
"""Check the exact client-source export boundary without creating an archive."""
import pathlib
import runpy
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/prepare-client-source.py"))


class SourceSelectionTest(unittest.TestCase):
    def test_exact_exclusions_and_active_inputs(self):
        excluded = MODULE["excluded_source"]
        for root in MODULE["EXCLUDED_SUBTREES"]:
            self.assertTrue(excluded(root + "manifest.json"))
            self.assertTrue(excluded(root + "packs/source.json"))
            self.assertFalse(excluded(root.rstrip("/") + "-other/manifest.json"))
        self.assertTrue(excluded("android/app/src/androidTest/java/co/fallsoft/vipi/ProfileSnapshotCompareDeviceTest.kt"))
        for path in ("data/immersion/all-pair-source-catalog-001.json", "data/lexical/catalog.json",
                     "language-packs/accepted-local-source-003/manifest.json",
                     "android/app/src/main/java/co/fallsoft/vipi/ChatSession.kt"):
            self.assertFalse(excluded(path), path)

    def test_integrated_tree_filters_every_experiment_descendant(self):
        revision = "2880451"
        result = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision, "--", "language-packs", "data", "android"], cwd=ROOT, text=True)
        names = result.splitlines()
        candidates = [n for n in names if any(n.startswith(p) for p in MODULE["EXCLUDED_SUBTREES"])]
        self.assertGreater(len(candidates), 0)
        selected = [n for n in names if not MODULE["excluded_source"](n)]
        self.assertTrue(all(n not in selected for n in candidates))
        self.assertIn("data/immersion/all-pair-source-catalog-001.json", selected)
        self.assertIn("data/lexical/catalog.json", selected)
        self.assertNotIn("android/app/src/androidTest/java/co/fallsoft/vipi/ProfileSnapshotCompareDeviceTest.kt", selected)


if __name__ == "__main__":
    unittest.main()
