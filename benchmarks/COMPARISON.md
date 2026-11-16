# Comparing scheduling algorithms

These experiments keep the public API, validation, timestamp rules, production
CLI, and existing tests fixed. Only schedule construction changes. Each candidate
has its own branch and working directory; no alternative has been merged into
`master`.

| Variant | Branch | How it works |
| --- | --- | --- |
| Baseline | `codex/benchmark-schedule-renderer` | Sort all ownership boundaries, then scan the overrides for each interval. |
| Boundary sweep | `codex/experiment-boundary-sweep` | Keep the boundary algorithm but advance a single index through sorted overrides. |
| Gap filling | `codex/experiment-gap-fill` | Emit each override directly and generate normal rotation only in uncovered gaps. |

The benchmark and experiments build on the still-unmerged benchmark PR #2.
Their PRs target that branch so the algorithm changes can be reviewed separately
from the original benchmark work.

## Correctness and fair timing

- All three variants pass the same 35 tests on Python 3.11 and 3.14, including
  exact boundaries, fractional seconds, overlapping-input rejection, timezone
  offsets, clipping, and the existing 50 seeded ownership scenarios.
- Before comparison, all variants must also match an independent minute-by-minute
  reference on 100 generated scenarios. They vary user count, handover interval,
  query clipping, override order, gaps, and cover users.
- Six measured workloads are checked against an independent hourly reference:
  no overrides, 99 separated overrides, the same dense case about 20 years later,
  one override covering the entire query, 99 touching overrides with alternating
  owners, and daily handovers with 99 separated overrides.
- All workloads last three weeks. Each timed invocation includes validation,
  timestamp parsing, construction, coalescing, and formatting of the result.
  The Python interpreter and CLI entry point are identical across candidates.
- The harness loads each scheduler into its own module and uses shared fixture
  and measurement code. It runs candidates sequentially, never concurrently.
- Each of nine rounds shuffles all variant/workload pairs using seed 2026. For
  each pair it warms up 20 function calls, times a batch of 500 calls, warms up
  one CLI launch, then times three CLI launches. This yields nine function batch
  averages and 27 CLI samples per candidate/workload. Function output is checked
  before and after each batch; every CLI output is checked. Those comparisons
  and fixture setup are outside the timed regions.
- Function results are medians of per-call batch averages. CLI results are
  medians of individual process-launch timings, including Python startup,
  imports, files, JSON output, and parent capture overhead. Filesystem caches
  are warmed. Garbage collection uses normal interpreter settings.
- The JSON report retains every timing sample, the shuffled execution order,
  exact candidate commits, scheduler source hashes, harness hashes, and settings.
  These are local wall-time observations with no pass/fail timing thresholds.

## Reproducing the comparison

From the comparison branch, prepare isolated copies of the pinned candidates
(skip the worktree creation commands if those directories already exist):

```sh
git fetch origin
git switch codex/compare-schedule-algorithms
git worktree add --detach ../schedule-baseline 2e40a3ebc261ca3959409dab015a3c3031c661ae
git worktree add --detach ../schedule-sweep 56e2ce5bdbfe53bb9e609db7ac30df72302d9cb4
git worktree add --detach ../schedule-gap-fill 8daa734d6af160402b618962f4dfc0f2a6648d3c

python3 benchmarks/compare.py \
  --variant baseline=../schedule-baseline \
  --variant sweep=../schedule-sweep \
  --variant gap-fill=../schedule-gap-fill \
  --iterations 500 --repeat 9 --cli-runs 3 \
  --output dist/algorithm-comparison.json
```

Use `--iterations 1 --repeat 1 --cli-runs 1` for a quick correctness and
compatibility check. Those single-sample timings should not be used to rank the
implementations. The recorded full run uses Python 3.14.8 on an Apple M1 Max;
Python 3.11 was used for compatibility checks, not a second full performance run.

## Results

Recorded on 16 November 2026, Apple M1 Max, macOS 27.0.1, CPython 3.14.8.
Each value below is a function median in **milliseconds per call**, including
the common validation and formatting work:

| Three-week workload | Original | Boundary sweep | Gap filling |
| --- | ---: | ---: | ---: |
| No overrides | 0.0118 | 0.0118 | 0.0111 |
| 99 separated overrides | 1.2445 | 0.6594 | 0.6138 |
| Same dense case about 20 years later | 1.2513 | 0.6668 | 0.6235 |
| One full-window override | 0.0100 | 0.0098 | 0.0061 |
| 99 adjacent overrides | 0.6494 | 0.4174 | 0.3386 |
| Daily handovers, 99 separated overrides | 1.3209 | 0.6955 | 0.6404 |

For the separated-override case, the sweep is 1.89 times as fast as the original
and gap filling is 2.03 times as fast. Gap filling is about 7% faster than the
sweep there, saving about **0.046 ms per function call**. It has the lowest
function median in each measured case, though the no-override difference is
less than a microsecond and should not drive the choice.

The full CLI measurements are much closer and do not give a consistent ranking:

| Workload | Original CLI, ms | Sweep CLI, ms | Gap-filling CLI, ms |
| --- | ---: | ---: | ---: |
| 99 separated overrides | 47.5955 | 45.6589 | 46.7510 |
| Same dense case about 20 years later | 46.8975 | 46.1792 | 45.4552 |
| Daily handovers, 99 separated overrides | 47.0457 | 45.9843 | 46.0291 |

Do not describe this as a twofold improvement to the complete command: Python
startup, imports, file handling, JSON serialisation, and capture account for most
of the CLI time. Small differences can also reflect machine noise. No confidence
interval or significance test was performed, so small median differences are
observations from this run rather than a claim of a statistically reliable win.

The [complete JSON report](results/algorithm-comparison-python3.14.json) contains
all six workloads, raw samples, candidate commits, source hashes, and execution
order. The source hashes and sample counts were verified after recording.

## Complexity and maintenance tradeoffs

Let `M` be the number of input overrides, `H` the handovers in the query, and
`B <= H + 2M + 2` the number of candidate boundaries. All approaches share
override validation and sorting, which cost `O(M log M)`.

| Variant | Construction work after validation | Review considerations |
| --- | --- | --- |
| Baseline | `O(B log B + B*M)` | Straightforward invariant: ownership is constant between boundaries. Repeated override scanning is unnecessary work. |
| Boundary sweep | `O(B log B + B + M)` | Smallest change to the existing solution; preserves its explanation, adding an override index that only moves forward. |
| Gap filling | `O(H + M)` | Uses a cursor marking the end of emitted coverage and two small helpers. Avoids a global boundary list and skips overridden handovers. |

The gap-filling bound also includes gap fragments around overrides; their count
is bounded by `M + 1`. All algorithms keep the parsed overrides and result in
memory. The first two also store a boundary set/list. Memory differences are
inferred from the code, not measured in this benchmark.

Correctness and clarity matter most for this assessment. Function speed is
useful evidence, but the CLI includes startup and I/O, and none of these local
measurements establishes a production latency guarantee or an exhaustive worst
case. A small timing difference alone is not a reason to adopt a harder-to-explain
implementation.

## Recommendation for the take-home

My recommendation is **the boundary sweep** for this submission. This is a
judgement about the assessment's priorities, not a claim that it wins every
timing measurement:

1. Correctness is a prerequisite: all three pass the same checks.
2. Clarity and review scope carry the most weight after correctness. The sweep
   preserves the original boundary invariant and needs the smallest algorithm
   change: replace the repeated scan with a forward-only override index.
3. It captures most of the measured function improvement, bringing the dense
   case below 0.7 ms on this machine. The original was already adequate for the
   stated workload, so this is a modest improvement rather than a requirement.
4. Gap filling is a sound alternative and the function-speed winner. Choose it
   if the cursor-and-gaps explanation feels more natural to you or if repeated
   in-process calls become important. Its additional dense-case saving over the
   sweep is small compared with the overall command runtime.

For the video, you can explain the decision in your own words:

> I tried two alternatives while keeping the inputs and correctness checks the
> same. A forward-only sweep nearly halved scheduling time with 99 overrides.
> Gap filling was a little faster again, but the complete command was dominated
> by startup and I/O. I would choose the sweep because it keeps the original
> correctness argument and is the smallest change, rather than selecting purely
> on the fastest function measurement.

This report recommends a choice; it does not adopt either experiment. Merge the
benchmark foundation first if wanted, then select one algorithm PR. Keep the
other alternative as experimental evidence rather than merging both renderers.
