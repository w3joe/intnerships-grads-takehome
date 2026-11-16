"""Compare isolated scheduler branches with shared inputs and shuffled timing rounds."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = module_from_spec(spec)
    sys.modules[name] = module  # dataclasses need their defining module registered.
    spec.loader.exec_module(module)
    return module


BENCH = load_module("comparison_measurements", ROOT / "benchmark-schedule")


def comparison_cases():
    cases = BENCH.scenarios()
    baseline, dense, _ = cases
    cases.extend([
        BENCH.Scenario("full-window-override", baseline.schedule, [{
            "user": "dana", "start_at": BENCH.timestamp(baseline.start),
            "end_at": BENCH.timestamp(baseline.end),
        }], baseline.start, baseline.end),
        BENCH.Scenario("adjacent-99-overrides", baseline.schedule, [{
            "user": "dana" if index % 2 == 0 else "erin",
            "start_at": BENCH.timestamp(baseline.start + timedelta(hours=1 + index * 2)),
            "end_at": BENCH.timestamp(baseline.start + timedelta(hours=3 + index * 2)),
        } for index in reversed(range(99))], baseline.start, baseline.end),
        BENCH.Scenario("daily-99-overrides", {
            **dense.schedule, "handover_interval_days": 1,
        }, dense.overrides, dense.start, dense.end),
    ])
    return cases


def reference(case, quantum):
    """Visit each grid step; fixtures keep every transition on this grid."""
    anchor = datetime.fromisoformat(case.schedule["handover_start_at"])
    duration = timedelta(days=case.schedule["handover_interval_days"])
    users = case.schedule["users"]
    overrides = [
        (datetime.fromisoformat(item["start_at"]),
         datetime.fromisoformat(item["end_at"]), item["user"])
        for item in case.overrides
    ]
    result = []
    current = max(anchor, case.start)
    while current < case.end:
        user = users[((current - anchor) // duration) % len(users)]
        for start, end, covering_user in overrides:
            if start <= current < end:
                user = covering_user
                break
        end = min(current + quantum, case.end)
        if result and result[-1]["user"] == user:
            result[-1]["end_at"] = BENCH.timestamp(end)
        else:
            result.append({"user": user, "start_at": BENCH.timestamp(current),
                           "end_at": BENCH.timestamp(end)})
        current = end
    return result


def check_varied_inputs(variants):
    rng = random.Random(2026)
    for index in range(100):
        start = BENCH.ANCHOR + timedelta(minutes=rng.randint(-60, 48 * 60))
        end = start + timedelta(minutes=rng.randint(0, 48 * 60))
        users = [f"user-{i}" for i in range(rng.randint(1, 5))]
        schedule = {"users": users, "handover_start_at": BENCH.timestamp(BENCH.ANCHOR),
                    "handover_interval_days": rng.randint(1, 7)}
        overrides = []
        minute = rng.randint(0, 120)
        for _ in range(rng.randint(0, 30)):
            last = minute + rng.randint(1, 180)
            overrides.append({
                "user": rng.choice(users + ["cover"]),
                "start_at": BENCH.timestamp(BENCH.ANCHOR + timedelta(minutes=minute)),
                "end_at": BENCH.timestamp(BENCH.ANCHOR + timedelta(minutes=last)),
            })
            minute = last + rng.randint(0, 120)
        rng.shuffle(overrides)
        case = BENCH.Scenario(str(index), schedule, overrides, start, end)
        expected = reference(case, timedelta(minutes=1))
        for name, variant in variants.items():
            BENCH.check_output(variant["renderer"](
                schedule, overrides, BENCH.timestamp(start), BENCH.timestamp(end)
            ), expected, f"{name}, generated case {index}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", action="append", required=True, metavar="NAME=DIRECTORY")
    parser.add_argument("--iterations", type=BENCH.positive_integer, default=500)
    parser.add_argument("--repeat", type=BENCH.positive_integer, default=7)
    parser.add_argument("--cli-runs", type=BENCH.positive_integer, default=3,
                        help="CLI samples per scenario and round; default 3 (21 total)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    variants = {}
    for index, value in enumerate(args.variant):
        name, separator, directory = value.partition("=")
        if not separator or not name or name in variants:
            parser.error("variants must have unique names and use NAME=DIRECTORY")
        path = Path(directory).expanduser().resolve()
        # All variants must use the same production CLI, so only the scheduler varies.
        if (path / "render-schedule").read_bytes() != (ROOT / "render-schedule").read_bytes():
            parser.error(f"{name}: CLI differs from the common baseline")
        module = load_module(f"comparison_variant_{index}", path / "scheduler.py")
        variants[name] = {"path": path, "renderer": module.render_schedule}

    check_varied_inputs(variants)
    print("All variants passed 100 generated cases against the minute-by-minute reference.",
          flush=True)
    cases = comparison_cases()
    expected = {case.name: reference(case, timedelta(hours=1)) for case in cases}
    samples = {name: {case.name: {"function": [], "cli": []} for case in cases}
               for name in variants}
    for name, variant in variants.items():
        for case in cases:
            BENCH.check_output(variant["renderer"](
                case.schedule, case.overrides, BENCH.timestamp(case.start),
                BENCH.timestamp(case.end)
            ), expected[case.name], f"{name}, {case.name}")

    rng = random.Random(2026)
    round_orders = []
    with tempfile.TemporaryDirectory(prefix="schedule-comparison-") as temporary:
        for round_index in range(args.repeat):
            tasks = [(name, case) for name in variants for case in cases]
            rng.shuffle(tasks)
            round_orders.append([f"{name}/{case.name}" for name, case in tasks])
            for name, case in tasks:
                variant = variants[name]
                function = BENCH.measure_function(
                    case, expected[case.name], args.iterations, 1,
                    renderer=variant["renderer"],
                )
                cli = BENCH.measure_cli(
                    case, expected[case.name], Path(temporary), args.cli_runs,
                    executable=variant["path"] / "render-schedule",
                )
                samples[name][case.name]["function"].extend(function["samples_ms_per_call"])
                samples[name][case.name]["cli"].extend(cli["samples_ms_per_call"])
            print(f"Completed timing round {round_index + 1}/{args.repeat}", flush=True)

    report = {
        "recorded_at_utc": BENCH.timestamp(datetime.now(timezone.utc)),
        "python": platform.python_version(), "platform": platform.platform(),
        "architecture": platform.machine(), "seed": 2026,
        "iterations_per_batch": args.iterations, "rounds": args.repeat,
        "cli_runs_per_round": args.cli_runs,
        "warmup_per_round": {"function_calls": 20, "cli_launches": 1},
        "timer": "perf_counter_ns", "gc_policy": "normal interpreter defaults",
        "generated_correctness_cases": 100, "round_orders": round_orders,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "measurement_helper_sha256": hashlib.sha256((ROOT / "benchmark-schedule").read_bytes()).hexdigest(),
        "variants": {},
    }
    print(f"\n{'Variant / scenario':<48} {'Function ms':>12} {'CLI ms':>12}")
    for name, variant in variants.items():
        report["variants"][name] = {
            "commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=variant["path"], text=True
            ).strip(),
            "scheduler_sha256": hashlib.sha256((variant["path"] / "scheduler.py").read_bytes()).hexdigest(),
            "scenarios": [],
        }
        for case in cases:
            data = samples[name][case.name]
            function, cli = BENCH.summary(data["function"]), BENCH.summary(data["cli"])
            report["variants"][name]["scenarios"].append({
                "name": case.name, "from": BENCH.timestamp(case.start),
                "until": BENCH.timestamp(case.end), "overrides": len(case.overrides),
                "handover_interval_days": case.schedule["handover_interval_days"],
                "entries": len(expected[case.name]), "function": function, "cli": cli,
            })
            print(f"{name + ' / ' + case.name:<48} "
                  f"{function['median_ms_per_call']:>12.4f} "
                  f"{cli['median_ms_per_call']:>12.4f}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"JSON report: {args.output}")


if __name__ == "__main__":
    main()
