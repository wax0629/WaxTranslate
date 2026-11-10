"""Browse, validate, export and run the Windows regression catalog (stdlib only)."""
import argparse
import ast
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "Tests/Fixtures/windows-regression.json"
CSV_PATH = ROOT / "docs/verification/windows-regression/cases.csv"
CSV_COLUMNS = ("编号", "模块", "优先级", "执行层", "用例", "输入数据", "命中词", "命中范围（Python字符索引）",
               "前置条件", "操作步骤", "预期结果", "自动检查", "参考检查")


def source_tests(root=ROOT):
    result = set()
    for path in [root / "windows/check.py", *sorted((root / "windows").glob("test_*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                for method in cls.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test_"):
                        result.add(f"{path.relative_to(root).as_posix()}::{cls.name}.{method.name}")
    return result


def selection(data):
    if not data.get("target"):
        return None
    text, target = data.get("text", ""), data["target"]
    occurrence = data.get("occurrence", 0)
    if type(occurrence) is not int or occurrence < 0:
        raise ValueError("occurrence 必须是从0开始的整数")
    spans = [match.span() for match in re.finditer(re.escape(target), text)]
    if occurrence >= len(spans):
        raise ValueError(f"输入中不存在第{occurrence + 1}个 {target!r}")
    return spans[occurrence]


def validate(catalog, root=ROOT):
    if catalog.get("schema") != 1 or catalog.get("platform") != "Windows":
        raise ValueError("不支持的测试集格式或平台")
    groups = catalog.get("groups", {})
    if not groups or not all(isinstance(k, str) and isinstance(v, str) for k, v in groups.items()):
        raise ValueError("groups 必须包含模块编号和名称")
    available = source_tests(root)
    seen = set()
    cases = catalog.get("cases", [])
    if not cases:
        raise ValueError("测试集没有用例")
    for case in cases:
        identity = case.get("id", "")
        if not re.fullmatch(r"WT-[A-Z]+-\d{3}", identity) or identity in seen:
            raise ValueError(f"用例编号无效或重复: {identity}")
        seen.add(identity)
        if case.get("group") not in groups or case.get("priority") not in ("P0", "P1"):
            raise ValueError(f"{identity}: 模块或优先级无效")
        if case.get("execution") not in ("offscreen", "desktop", "manual"):
            raise ValueError(f"{identity}: 执行层无效")
        if not isinstance(case.get("title"), str) or not case["title"].strip():
            raise ValueError(f"{identity}: 缺少标题")
        for field in ("preconditions", "steps", "expected"):
            if not isinstance(case.get(field), list) or not case[field] or not all(isinstance(x, str) and x.strip() for x in case[field]):
                raise ValueError(f"{identity}: {field} 必须包含可检查的文字")
        tests = case.get("automation", [])
        related = case.get("related_tests", [])
        if not isinstance(tests, list) or not isinstance(related, list):
            raise ValueError(f"{identity}: 自动检查引用必须是列表")
        if case["execution"] == "manual" and tests:
            raise ValueError(f"{identity}: 纯人工用例不能声明自动通过")
        if case["execution"] != "manual" and not tests:
            raise ValueError(f"{identity}: 缺少自动执行入口")
        for reference in tests + related:
            if reference not in available:
                raise ValueError(f"{identity}: 自动检查引用不存在: {reference}")
        if case["execution"] == "offscreen" and any(".test_desktop_" in ref for ref in tests):
            raise ValueError(f"{identity}: 桌面检查不能声明为离屏")
        try:
            selection(case.get("data", {}))
        except (ValueError, TypeError) as error:
            raise ValueError(f"{identity}: {error}") from error
        for fixture in case.get("fixtures", []):
            relative = Path(fixture["path"])
            path = (root / relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f"{identity}: 语料路径无效: {relative}")
            if fixture.get("ids"):
                corpus = json.loads(path.read_text(encoding="utf-8"))
                known = {x["id"] for x in corpus["cases"]}
                if not set(fixture["ids"]) <= known:
                    raise ValueError(f"{identity}: 语料编号不存在")
    return available


def select_cases(catalog, groups=(), identities=(), priority=None):
    unknown = set(groups) - catalog["groups"].keys()
    missing = set(identities) - {x["id"] for x in catalog["cases"]}
    if unknown or missing:
        raise ValueError(f"未知模块或用例: {sorted(unknown | missing)}")
    return [case for case in catalog["cases"]
            if (not groups or case["group"] in groups)
            and (not identities or case["id"] in identities)
            and (priority is None or case["priority"] == priority)]


def csv_rows(catalog):
    rows = [list(CSV_COLUMNS)]
    for case in catalog["cases"]:
        data = case.get("data", {})
        span = selection(data)
        refs = [f"{x['path']}#{','.join(x.get('ids', []))}" for x in case.get("fixtures", [])]
        rows.append([case["id"], catalog["groups"][case["group"]], case["priority"], case["execution"],
                     case["title"], data.get("text", data.get("description", "\n".join(refs))),
                     data.get("target", ""), f"[{span[0]}, {span[1]})" if span else "",
                     "\n".join(case["preconditions"]), "\n".join(case["steps"]), "\n".join(case["expected"]),
                     "\n".join(case.get("automation", [])), "\n".join(case.get("related_tests", []))])
    return rows


def export_csv(catalog, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(csv_rows(catalog))


def check_csv(catalog, path=CSV_PATH):
    actual = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    if actual != csv_rows(catalog):
        raise ValueError("CSV与JSON不同步，请运行 export 更新")


def command_for(cases, *, full=False, desktop=False, executable=sys.executable):
    command = [executable, "-X", "utf8", str(ROOT / "windows/check.py"), "-v"]
    if desktop:
        command.append("--desktop")
    if full:
        return command
    references = {ref for case in cases if case["execution"] == "offscreen" or
                  (desktop and case["execution"] == "desktop") for ref in case.get("automation", [])}
    if not references:
        raise ValueError("所选用例没有可执行的自动检查；人工项请按CSV中的步骤验收")
    for reference in sorted(references):
        path, name = reference.split("::", 1)
        selector = name if Path(path).stem == "check" else f"{Path(path).stem}.{name}"
        command.extend(("-k", selector))
    return command


def summary(output, code):
    found = re.search(r"Ran (\d+) tests? in ([\d.]+)s", output)
    skipped = re.search(r"skipped=(\d+)", output)
    count = int(found[1]) if found else 0
    skip = int(skipped[1]) if skipped else 0
    return {"status": "passed" if code == 0 and count > skip else "failed" if code else "unverified",
            "tests": count, "skipped": skip, "seconds": float(found[2]) if found else None,
            "exit_code": code}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    for verb in ("list", "run"):
        action = sub.add_parser(verb)
        action.add_argument("--group", action="append", default=[])
        action.add_argument("--case", dest="identities", action="append", default=[])
        action.add_argument("--priority", choices=("P0", "P1"))
        if verb == "run":
            action.add_argument("--full", action="store_true", help="执行现有全部自动检查，不按目录筛选")
            action.add_argument("--desktop", action="store_true", help="真实桌面：显示窗口、移动鼠标、发送按键；仅在独立runner或已获同意的桌面使用")
            action.add_argument("--report", type=Path)
    sub.add_parser("check")
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path, default=CSV_PATH)
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["list"])
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        available = validate(catalog)
        if args.command == "export":
            export_csv(catalog, args.output)
            print(args.output)
            return 0
        if args.command == "check":
            check_csv(catalog)
            print(f"Catalog OK: {len(catalog['cases'])} cases; {len(available)} existing automated tests; CSV matches.")
            return 0
        selected = select_cases(catalog, args.group, args.identities, args.priority)
        if not selected:
            raise ValueError("没有符合筛选条件的用例")
        if args.command == "list":
            for case in selected:
                print(f"{case['id']}  {case['priority']}  {case['execution']:9}  {case['title']}")
            print(f"{len(selected)} cases")
            return 0
        if sys.platform != "win32":
            raise ValueError("执行应用检查需要Windows；list/check/export可跨平台使用")
        if args.full and (args.group or args.identities or args.priority):
            raise ValueError("--full不能与用例筛选同时使用")
        command = command_for(selected, full=args.full, desktop=args.desktop)
        print("Running: " + subprocess.list2cmdline(command), flush=True)
        completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        print(completed.stdout, end="")
        result = summary(completed.stdout, completed.returncode)
        pending = [x["id"] for x in selected if x["execution"] == "manual" or
                   (not args.desktop and x["execution"] == "desktop")]
        result["automation_status"] = result["status"]
        if result["status"] == "passed" and (pending or result["skipped"]):
            result["status"] = "partial"
        result.update(command=command, selected_cases=[x["id"] for x in selected],
                      pending_manual_or_desktop=pending, timestamp_utc=datetime.now(timezone.utc).isoformat())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        report = args.report or ROOT / "dist/regression" / f"{stamp}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report.with_suffix(".log").write_text(completed.stdout, encoding="utf-8")
        print(f"Report: {report}")
        print(f"Automatic checks: {result['automation_status']}; catalog coverage: {result['status']}")
        print(f"Pending manual/desktop cases: {len(pending)}")
        return completed.returncode or (0 if result["automation_status"] == "passed" else 2)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
