# Comparing six scheduling algorithms

These experiments hold the public API, validation, timestamp rules, CLI, and
existing tests fixed while changing schedule construction. Every candidate has
its own branch and working directory. No alternative has been merged into
`master`. The experiments and this comparison build on benchmark PR #2.

| Variant | Branch | How it works |
| --- | --- | --- |
| [Original](https://github.com/w3joe/intnerships-grads-takehome/pull/2) | `codex/benchmark-schedule-renderer` | Sort ownership boundaries, then scan overrides for each interval. |
| [Boundary sweep](https://github.com/w3joe/intnerships-grads-takehome/pull/3) | `codex/experiment-boundary-sweep` | Keep the boundaries and advance one index through sorted overrides. |
| [Gap filling](https://github.com/w3joe/intnerships-grads-takehome/pull/4) | `codex/experiment-gap-fill` | Emit overrides directly and generate normal rotation in the gaps. |
| [Binary search](https://github.com/w3joe/intnerships-grads-takehome/pull/6) | `codex/experiment-binary-search` | Binary-search override start times for the candidate covering each boundary interval. |
| [Event sweep](https://github.com/w3joe/intnerships-grads-takehome/pull/7) | `codex/experiment-event-sweep` | Process timestamped ownership changes while tracking normal and override owners. |
| [Interval overlay](https://github.com/w3joe/intnerships-grads-takehome/pull/8) | `codex/experiment-interval-overlay` | Generate normal coverage, then split its intervals around each override. |

## Correctness and measurement method

- All six implementations pass the same 35 tests on Python 3.11 and 3.14,
  including clipping, fractional seconds, timezone offsets, invalid inputs, and
  adjacent overrides meeting at a handover. The suite includes 50 seeded
  ownership scenarios.
- Before timing, all six also match an independent minute-by-minute reference
  on 100 generated inputs varying users, handover intervals, clipping, override
  order, gaps, and cover users. Both Python versions pass this comparison check.
- All six measured workloads match an independent hourly reference. Their
  transitions fall on hour boundaries, so that reference covers their complete
  expected output. All queries span three weeks with fewer than 100 overrides.
- The model, parsing, validation, and timestamp-formatting helper ASTs were checked
  against the original, and the production CLI files were checked byte-for-byte.
  Candidates do not cache repeated calls or special-case benchmark fixtures.
- One common harness loads the candidates as separate modules and runs them
  sequentially. Each of nine rounds shuffles all 36 candidate/workload pairs with
  seed 2026. Earlier candidates are remeasured in the same run as the new ones;
  rankings do not combine timings from different sessions.
- For each pair per round, warm up 20 function calls and time 500 calls as one
  batch. Report the median of the nine per-call batch averages. This includes
  validation, timestamp parsing, scheduling, coalescing, and JSON-ready formatting.
- Warm up one CLI launch per pair per round, then time three launches, yielding
  27 timed samples. Report their median. This includes Python startup, imports,
  file reads, scheduling, JSON serialisation, and parent output capture. Filesystem
  caches are warm; each CLI sample still uses a fresh Python process.
- Function results are checked before and after each batch; every CLI output is
  checked. Reference comparisons and fixture setup are outside the timed regions.
  `perf_counter_ns` measures wall time, with normal garbage-collection settings.
- The JSON report retains all samples, shuffled execution order, exact candidate
  commits, source hashes, harness hashes, and settings. Source hashes and sample
  counts were verified after recording. There are no timing pass/fail thresholds.

## Expanded results

Recorded on 16 November 2026 on an Apple M1 Max, macOS 27.0.1, CPython 3.14.8.
Function medians below are **milliseconds per call**:

| Three-week workload | Original | Sweep | Gap fill | Binary search | Events | Overlay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No overrides | 0.0118 | 0.0117 | 0.0111 | 0.0119 | 0.0111 | 0.0102 |
| 99 separated overrides | 1.2405 | 0.6562 | 0.6077 | 0.6618 | 0.5681 | 0.8894 |
| Same dense case ~20 years later | 1.2483 | 0.6617 | 0.6148 | 0.6663 | 0.5708 | 0.8927 |
| One full-window override | 0.0101 | 0.0099 | 0.0062 | 0.0100 | 0.0091 | 0.0101 |
| 99 adjacent overrides | 0.6461 | 0.4140 | 0.3333 | 0.4175 | 0.3624 | 0.5407 |
| Daily handovers, 99 overrides | 1.3123 | 0.6918 | 0.6305 | 0.6979 | 0.5995 | 0.9956 |

The event sweep has the lowest medians on the separated, late, and daily-handover
99-override cases. On the separated case it is about 2.18 times as fast as the
original. Gap filling wins the adjacent and full-window cases. Overlay is fastest
on the no-override case, but that saves only about 1.6 microseconds over the
original; it is slower than the other new candidates on the dense cases.

Full CLI results for 99 separated overrides:

| Approach | Function, ms/call | Full CLI, ms/call |
| --- | ---: | ---: |
| Original | 1.2405 | 45.7427 |
| Boundary sweep | 0.6562 | 44.9228 |
| Gap filling | 0.6077 | 44.8235 |
| Binary search | 0.6618 | 44.9850 |
| Event sweep | 0.5681 | 44.5293 |
| Interval overlay | 0.8894 | 45.0360 |

Do not call the event implementation a 2.18-times-faster complete command: the
CLI stays around 44–46 ms, and most elapsed time is outside the scheduling
function. Differences in imports, process startup, system load, and I/O all affect
these measurements. No confidence intervals or significance tests were performed,
so small differences are observations from this run rather than claims of a
statistically reliable advantage.

The [six-way JSON report](results/six-algorithm-comparison-python3.14.json) is the
source for these tables. The [earlier three-way report](results/algorithm-comparison-python3.14.json)
is retained as historical evidence; use the new side-by-side run when comparing
all six. Python 3.11 was used for compatibility checks, not a second full timing run.

## Complexity and review tradeoffs

Let `M` be the input overrides, `H` the in-window handovers, `B` the candidate
boundaries, and `E` the ownership events. Both `B` and `E` are at most
`H + 2M + 2`. All approaches share `O(M log M)` validation and override sorting.

| Approach | Construction after validation | Main tradeoff |
| --- | --- | --- |
| Original | `O(B log B + B*M)` | Simple boundary invariant; repeated scanning costs extra work. |
| Boundary sweep | `O(B log B + B + M)` | Smallest algorithm change, preserving the original explanation and adding one forward-only index. |
| Gap filling | `O(H + M)` | Avoids a global boundary list, but introduces a coverage cursor and gap-rendering/coalescing helpers. |
| Binary search | `O(B log B + B log(M+1) + M)` | Compact, stateless lookup for each interval; no observed speed advantage over the forward sweep on chronological inputs. |
| Event sweep | `O(E log E + M)` | Avoids repeated ownership queries and rotation division for output fragments; needs explicit event priority, grouping, and two owner states. |
| Interval overlay | `O((M+1)*(H+M+1))` | Directly models replacing existing coverage; rescans and rebuilds the interval list per override. |

The gap-filling bound includes normal fragments around overrides, whose number
is bounded by `H + M + 1`. All approaches store parsed overrides and results.
The boundary approaches also store a boundary collection, binary search adds a
start-time array, events use an event list, and overlay rebuilds a temporary list
per pass. These memory differences are inferred from the code, not measured.

## Recommendation

For the take-home, I still recommend **the boundary sweep as the balanced choice**:

1. Correctness is mandatory; all six pass the same checks.
2. Clarity and review scope matter most after correctness. The sweep is the
   smallest change and preserves the already-understood boundary invariant.
3. Its separated-override median is about 0.656 ms instead of 1.241 ms. The event
   version saves another 0.088 ms in that case, but adds simultaneous-event order
   and state tracking. That extra speed is small relative to the full command.
4. If function throughput is your main goal, shortlist **event sweep and gap
   filling**. Events win several dense cases; gap filling wins others. There is
   no universal fastest implementation across the tested shapes.
5. Binary search offers no observed advantage here. It would be a more natural
   design for independent point queries, whereas this renderer visits intervals
   in chronological order. Overlay is intuitive, but not the best throughput
   choice among these implementations.

This weights clarity and reviewability above small timing differences for the
assessment's bounded workload. All implementations already operate comfortably
within these small measured inputs; there is no specified latency target.
Choose a different candidate if its explanation is clearer to you, rather than
claiming there is one objectively best algorithm from this local run.

For the video, explain the measured tradeoff in your own words:

> I compared six approaches with identical inputs and correctness checks. A
> forward-only sweep nearly halved scheduling time while keeping the original
> boundary explanation. An event-based version was fastest on the dense case,
> but saved less than a tenth of a millisecond beyond the sweep and required
> more state and tie-order rules. I would choose the sweep for this workload,
> while keeping the other measurements as evidence for that decision.

## Reproducing the full comparison

From the comparison branch, prepare isolated copies of the pinned candidates.
Skip creation commands for directories you have already created:

```sh
git fetch origin
git switch codex/compare-schedule-algorithms
git worktree add --detach ../schedule-baseline 2e40a3ebc261ca3959409dab015a3c3031c661ae
git worktree add --detach ../schedule-sweep 56e2ce5bdbfe53bb9e609db7ac30df72302d9cb4
git worktree add --detach ../schedule-gap-fill 8daa734d6af160402b618962f4dfc0f2a6648d3c
git worktree add --detach ../schedule-binary-search 956b8420adfb7796b61993a748a4559c1a8cf2fb
git worktree add --detach ../schedule-events e7a903666d05632dcf8ebf98976db5d480a9addf
git worktree add --detach ../schedule-overlay 90261c6512bf1f6a6ce791a47b78e73043526fd8

python3 benchmarks/compare.py \
  --variant baseline=../schedule-baseline \
  --variant sweep=../schedule-sweep \
  --variant gap-fill=../schedule-gap-fill \
  --variant binary-search=../schedule-binary-search \
  --variant events=../schedule-events \
  --variant overlay=../schedule-overlay \
  --iterations 500 --repeat 9 --cli-runs 3 \
  --output dist/six-algorithm-comparison.json
```

Use `--iterations 1 --repeat 1 --cli-runs 1` for a quick correctness check, not
for performance ranking. CI checks the shared harness on the current candidate;
all isolated candidates were checked together locally on both Python versions.
The full local run uses nine rounds and the settings above.

The candidate PRs remain drafts and nothing is adopted by this report. If wanted,
merge benchmark PR #2 first, then select one algorithm PR. Keep the alternatives
as experiments rather than merging multiple renderers into the submission.
