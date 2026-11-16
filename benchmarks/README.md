# Schedule performance measurements

Run from the repository root with Python 3.11 or newer; no extra dependencies are
needed:

```sh
./benchmark-schedule --output dist/benchmark-results.json
```

The command prints a comparison table and saves a JSON report with all timing
samples, Python and platform details, the measurement settings, input sizes, and
a SHA-256 hash of the scheduler source. The output directory is created if needed.
Use `python3 benchmark-schedule` if executable permissions are unavailable.

## Workloads

All cases use three rotating users, weekly handovers, and a 21-day query window.

| Scenario | Overrides | Purpose |
| --- | ---: | --- |
| `baseline` | 0 | Measure the simple rotation. |
| `99-overrides` | 99 | Exercise inputs near the assessment's stated override limit. |
| `late-99-overrides` | 99 | Repeat the dense workload about 20 years after the schedule anchor. |

The dense cases contain two-hour overrides beginning every five hours, supplied
in reverse chronological order. They are valid and non-overlapping. The late
window is shifted by 350 complete three-week rotations (7,350 days), so it has
the same rotation phase and output shape as the earlier dense window.

This comparison controls the work inside the query window while changing the
amount of schedule history. The implementation calculates the active shift
directly; it does not generate all preceding shifts.

## Correctness before timing

An independent reference visits each hour of the query, assigns its owner, and
combines consecutive hours with the same owner. All fixture transitions fall on
hour boundaries, so this checks the complete expected output for these cases.
The reference does not use the production boundary-partition algorithm.

The scheduling function must match that reference before timing starts and after
the function timing finishes. Every CLI run must also return the expected JSON
with no stderr. A mismatch stops the command with a nonzero exit code.

These checks complement the existing scheduling tests, which also cover
fractional-second transitions, clipping, timezone offsets, and invalid inputs.

## Timing method

- Use `perf_counter_ns` to measure elapsed wall time. Fixture generation and
  reference calculation happen outside the timed regions.
- **Function:** start from decoded JSON inputs and prepared query strings. Warm
  up with 20 calls, then run seven batches of 1,000 calls. Divide each batch's
  duration by 1,000 and report the median of those seven per-call averages. This
  includes input validation, timestamp parsing, scheduling, and construction of
  the JSON-ready result, with normal interpreter garbage-collection settings.
- **CLI:** create input files outside the timed region. Warm up with one process
  launch, then measure 21 separate launches using the same Python interpreter
  as the benchmark. Report the median. This includes process startup, imports,
  file reads, scheduling, JSON serialisation, and output capture by the parent.
  Comparing the captured JSON with the reference happens after timing each run.
- Keep all samples plus the minimum, median, and maximum in the JSON report.
  There are no performance assertions or thresholds.

The CLI measurements use warmed filesystem caches and still start a fresh Python
process each time. These are local steady-state timings, not a cold-boot test,
concurrent load test, memory benchmark, or production latency guarantee. Machine
load and Python version can affect the results.

For a quick compatibility and correctness check:

```sh
./benchmark-schedule --iterations 1 --repeat 1 --cli-runs 1
python3 -m unittest discover -s tests -v
```

CI runs that small benchmark check on Python 3.11 and 3.14 and also verifies JSON
report creation. It does not use those timings as performance measurements or
enforce timing thresholds. Use the default, larger sample counts for reporting.

## Recorded local results

Measured on 16 November 2026 on an Apple M1 Max (arm64), macOS 27.0.1, with
CPython 3.14.8. This run used the default seven batches of 1,000 function calls
and 21 CLI launches per case. All correctness checks passed.

| Scenario | Output entries | Function median, ms/call | CLI median, ms/call |
| --- | ---: | ---: | ---: |
| Baseline | 3 | 0.0117 | 46.8703 |
| 99 overrides | 199 | 1.2686 | 49.0829 |
| Same dense workload about 20 years later | 199 | 1.2870 | 47.3427 |

The full settings and unrounded samples are in
[`results/apple-m1-max-python3.14.json`](results/apple-m1-max-python3.14.json).
The scheduler source hash in that report identifies the implementation measured.

The dense function timings are similar despite the later schedule position,
consistent with directly calculating the active rotation index. The difference
between function and CLI timings includes interpreter startup, imports, input
and output handling, and parent process overhead. It should not be attributed
entirely to the scheduling calculation.

These local results support keeping the straightforward implementation for the
stated small workloads. They do not establish an exhaustive worst case or a
latency promise for other machines or input distributions.

These are measurements of the original algorithm. For fresh side-by-side results
across six implementations, see the [algorithm comparison](COMPARISON.md).

For the video, a concise explanation of the original implementation is:

> I prioritised correctness and checked the implementation with representative
> benchmarks. On this machine, the scheduling function took a median of about
> 1.3 milliseconds with 99 overrides across three weeks, while the full command
> took about 49 milliseconds including startup and I/O. Moving the same workload
> about 20 years later produced similar function timings, consistent with
> calculating the active shift directly rather than replaying the history.
