"""Summarize real lookup JSONL; failures and >1 s samples stay in the denominator."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics


def summarize(rows):
    times = sorted(row["milliseconds"] for row in rows)
    return {
        "samples": len(rows), "p50_ms": round(statistics.median(times), 1),
        "p95_ms": round(times[math.ceil(len(times) * .95) - 1], 1), "max_ms": round(times[-1], 1),
        "over_1s": sum(value > 1000 for value in times),
        "quality_pass": sum(row.get("quality") is True for row in rows),
        "quality_fail": sum(row.get("quality") is False for row in rows),
        "quality_unscored": sum(row.get("quality") is None for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--require-target", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(line) for path in args.reports for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        parser.error("No completed samples; a skipped/failed run is not a pass")
    groups = defaultdict(list)
    for row in rows:
        groups["cached" if row.get("cacheHit") else "uncached"].append(row)
    print(json.dumps({name: summarize(group) for name, group in groups.items()}, ensure_ascii=False, indent=2))
    if args.csv:
        with args.csv.open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["sample", "iteration", "cache", "ms", "quality", "stage", "duration_ms", "elapsed_ms"])
            for row in rows:
                for event in row["events"]:
                    writer.writerow([row["id"], row["iteration"], row.get("cacheHit", False),
                                     round(row["milliseconds"], 1), row.get("quality", "unscored"), event["stage"],
                                     round(event["durationMs"], 1), round(event["elapsedMs"], 1)])
    failures = [dict(id=row["id"], iteration=row["iteration"], ms=round(row["milliseconds"], 1),
                     quality=row.get("quality")) for row in rows if row["milliseconds"] > 1000 or row.get("quality") is False]
    print(json.dumps({"failed_target_samples": failures}, ensure_ascii=False, indent=2))
    if args.require_target and (failures or any(row.get("quality") is not True for row in rows)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
