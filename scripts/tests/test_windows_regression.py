"""Catalog integrity and safe CLI dispatch; no Qt, models or desktop required."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("windows_regression", ROOT / "scripts/windows_regression.py")
catalog_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog_tool)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(catalog_tool.CATALOG.read_text(encoding="utf-8"))

    def test_all_references_and_csv_are_current(self):
        self.assertGreaterEqual(len(self.catalog["cases"]), 40)
        self.assertTrue(catalog_tool.validate(self.catalog))
        catalog_tool.check_csv(self.catalog)

    def test_duplicate_ids_are_rejected(self):
        self.catalog["cases"].append(deepcopy(self.catalog["cases"][0]))
        with self.assertRaisesRegex(ValueError, "重复"):
            catalog_tool.validate(self.catalog)

    def test_missing_test_reference_is_rejected(self):
        self.catalog["cases"][0]["automation"] = ["windows/check.py::Checks.test_missing"]
        with self.assertRaisesRegex(ValueError, "引用不存在"):
            catalog_tool.validate(self.catalog)

    def test_manual_and_desktop_are_not_claimed_as_offscreen(self):
        manual = next(x for x in self.catalog["cases"] if x["execution"] == "manual")
        manual["automation"] = self.catalog["cases"][0]["automation"]
        with self.assertRaisesRegex(ValueError, "纯人工"):
            catalog_tool.validate(self.catalog)
        manual["automation"] = []
        desktop = next(x for x in self.catalog["cases"] if x["execution"] == "desktop")
        desktop["execution"] = "offscreen"
        with self.assertRaisesRegex(ValueError, "桌面检查"):
            catalog_tool.validate(self.catalog)

    def test_missing_expectations_and_invalid_occurrence_are_rejected(self):
        self.catalog["cases"][0]["expected"] = "not a list"
        with self.assertRaisesRegex(ValueError, "expected"):
            catalog_tool.validate(self.catalog)
        with self.assertRaises(ValueError):
            catalog_tool.selection({"text": "token token", "target": "token", "occurrence": 2})
        self.assertEqual(catalog_tool.selection({"text": "模型token与访问token", "target": "token", "occurrence": 1}), (10, 15))

    def test_invalid_fixture_ids_and_escaping_paths_are_rejected(self):
        case = next(x for x in self.catalog["cases"] if x.get("fixtures"))
        case["fixtures"][0]["ids"] = ["missing-case"]
        with self.assertRaisesRegex(ValueError, "语料编号"):
            catalog_tool.validate(self.catalog)
        case["fixtures"] = [{"path": "../../outside.json"}]
        with self.assertRaisesRegex(ValueError, "语料路径"):
            catalog_tool.validate(self.catalog)

    def test_group_selection_and_unknown_filters(self):
        selected = catalog_tool.select_cases(self.catalog, groups=["window"], priority="P0")
        self.assertTrue(selected)
        self.assertTrue(all(x["group"] == "window" and x["priority"] == "P0" for x in selected))
        with self.assertRaises(ValueError):
            catalog_tool.select_cases(self.catalog, identities=["WT-MISSING-001"])

    def test_desktop_requires_explicit_flag_and_tests_are_deduplicated(self):
        ordinary = self.catalog["cases"][0]
        desktop = next(x for x in self.catalog["cases"] if x["execution"] == "desktop")
        command = catalog_tool.command_for([ordinary, ordinary, desktop])
        self.assertNotIn("--desktop", command)
        self.assertEqual(command.count("-k"), 1)
        with_desktop = catalog_tool.command_for([ordinary, desktop], desktop=True)
        self.assertIn("--desktop", with_desktop)
        self.assertEqual(with_desktop.count("-k"), 2)
        manual = next(x for x in self.catalog["cases"] if x["execution"] == "manual")
        with self.assertRaises(ValueError):
            catalog_tool.command_for([manual])

    def test_csv_unicode_multiline_and_drift(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "cases.csv"
            catalog_tool.export_csv(self.catalog, path)
            self.assertEqual(path.read_bytes()[:3], b"\xef\xbb\xbf")
            catalog_tool.check_csv(self.catalog, path)
            path.write_text(path.read_text(encoding="utf-8-sig").replace("旧配置", "changed", 1), encoding="utf-8-sig")
            with self.assertRaisesRegex(ValueError, "不同步"):
                catalog_tool.check_csv(self.catalog, path)

    def test_empty_or_fully_skipped_run_is_not_a_pass(self):
        self.assertEqual(catalog_tool.summary("Ran 0 tests in 0.000s\nOK", 0)["status"], "unverified")
        self.assertEqual(catalog_tool.summary("Ran 1 test in 0.010s\nOK (skipped=1)", 0)["status"], "unverified")
        self.assertEqual(catalog_tool.summary("Ran 12 tests in 1.000s\nOK (skipped=2)", 0)["status"], "passed")
        self.assertEqual(catalog_tool.summary("Ran 12 tests in 1.000s\nFAILED (failures=1)", 1)["status"], "failed")
        self.assertEqual(catalog_tool.summary("Ran 120 tests in 1.000s\nOK", 3221226505)["status"], "failed")

    def test_no_arguments_only_lists_cases(self):
        with patch.object(catalog_tool.subprocess, "run") as run, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(catalog_tool.main([]), 0)
            self.assertIn(f"{len(self.catalog['cases'])} cases", output.getvalue())
            run.assert_not_called()

    def test_run_records_pending_cases_without_starting_manual_work(self):
        with TemporaryDirectory() as folder:
            report = Path(folder) / "report.json"
            result = SimpleNamespace(returncode=0, stdout="Ran 120 tests in 1.000s\nOK (skipped=4)\n")
            with patch.object(catalog_tool.sys, "platform", "win32"), \
                    patch.object(catalog_tool.subprocess, "run", return_value=result) as run, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(catalog_tool.main(["run", "--full", "--report", str(report)]), 0)
            command = run.call_args.args[0]
            self.assertNotIn("--desktop", command)
            self.assertEqual(run.call_args.kwargs["cwd"], ROOT)
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(saved["skipped"], 4)
            self.assertEqual(saved["automation_status"], "passed")
            self.assertEqual(saved["status"], "partial")
            self.assertTrue(saved["pending_manual_or_desktop"])
            self.assertTrue(report.with_suffix(".log").exists())

    def test_manual_only_selection_never_launches_a_process(self):
        manual = next(x for x in self.catalog["cases"] if x["execution"] == "manual")
        with patch.object(catalog_tool.sys, "platform", "win32"), \
                patch.object(catalog_tool.subprocess, "run") as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                catalog_tool.main(["run", "--case", manual["id"]])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
