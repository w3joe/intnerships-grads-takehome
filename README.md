# Internship, placement and graduate take home assessment

## Running the solution

Requires **Python 3.11 or newer** on macOS or Linux. There are no third-party
dependencies to install. Run these commands from the repository root:

```sh
./render-schedule \
  --schedule=examples/schedule.json \
  --overrides=examples/overrides.json \
  --from='2026-11-06T17:00:00Z' \
  --until='2026-11-20T17:00:00Z'
```

This reproduces the assessment example; the expected result is in
[`examples/expected.json`](examples/expected.json). The input files must contain
valid JSON (without comments). Use an empty array, `[]`, for no overrides.
Both `--argument=value` and `--argument value` are supported.

The executable writes only JSON to stdout on success. Errors go to stderr with
exit code 2. Run `./render-schedule --help` for argument help.

On Windows, invoke the program as `python render-schedule` with the same arguments.
If an extraction tool discards executable permissions on macOS or Linux, restore
them with `chmod +x render-schedule`.

## Implementation

- [`scheduler.py`](scheduler.py) contains the pure `render_schedule` function:
  decoded JSON and timestamp strings in, a JSON-ready list out, with no I/O or
  input mutation. Invalid inputs raise `ValueError`.
- [`render-schedule`](render-schedule) handles argument parsing, reading JSON files,
  printing results, and reporting errors.
- [`tests/`](tests/) contains scheduling and executable CLI tests.

The algorithm builds the normal schedule, then overlays temporary coverage:

1. Clip the query and generate the ordinary rotation entries inside it, starting
   directly at the active shift rather than replaying earlier schedule history.
2. Visit the validated overrides in chronological order.
3. For each override, walk the current entries. Keep entries that do not intersect
   it. Split intersecting entries into an optional original-owner prefix, the
   override-covered intersection, and an optional original-owner suffix.
4. Replace the entry list with those pieces, preserving chronological order.
5. After all overrides, merge touching entries with equal owners.

This directly models the meaning of an override as replacing part of an existing
schedule. Overrides spanning handovers may initially create several covered
fragments; final coalescing joins them. Rebuilding and scanning the entries for
each override trades throughput for an explicit before-and-after representation.

### Time rules and validation

- Intervals are half-open: `[start, end)`. An override ending exactly when another
  starts does not overlap it.
- Timestamps are timezone-aware ISO 8601 strings. `Z` and numeric UTC offsets are
  accepted; naive timestamps are rejected. Output uses UTC with a `Z` suffix.
  Fractional seconds are supported to Python datetime's microsecond precision.
- One interval day means exactly 24 elapsed hours in UTC. Named timezones and
  daylight-saving wall-clock scheduling are outside this input format.
- Before `handover_start_at` there is no coverage. Queries spanning that point
  start their output there; queries wholly before it return `[]`.
- Equal query endpoints return `[]`; an end before the start is an error.
- Users must be a nonempty array of nonempty strings. The handover interval must
  be a positive integer number of days.
- Overrides must have positive duration, start at or after the schedule start,
  and not overlap. They may be unsorted or name someone outside the rotation.
  Touching overrides are allowed. Overrides outside the query do not affect it.
- Adjacent entries with the same owner are merged, including across handovers
  and override boundaries. No zero-duration entries are emitted.

## Testing

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the assessment example, rotation wraparound, clipping, empty windows,
queries long after the schedule began, overrides crossing several handovers,
adjacent and unsorted overrides, same-owner merging, UTC offsets, fractional
seconds, invalid inputs, and CLI output streams and exit codes. The CLI is also
run from another working directory to check file and import behaviour.

A deterministic set of 50 generated scenarios compares the scheduler with an
independent hour-by-hour ownership reference and checks continuity and bounds.
All generated transitions are on hour boundaries; dedicated examples cover
sub-hour and fractional-second transitions.

GitHub Actions runs the suite on Python 3.11 and 3.14 on Linux for pushes and pull
requests. Changes use feature branches, Conventional Commit messages, and a pull
request into this fork's `master` branch.

## Performance measurements

Run `./benchmark-schedule --output dist/benchmark-results.json` for a validated
comparison of the scheduling function and full CLI on three representative
workloads. It uses only the standard library and has no timing-based pass/fail
thresholds. See [`benchmarks/README.md`](benchmarks/README.md) for the method,
recorded local results, and a short explanation for the video walkthrough.

## Creating the submission ZIP

After committing the changes you want to submit:

```sh
mkdir -p dist
git archive --format=zip --prefix=schedule-renderer/ \
  --output=dist/schedule-renderer.zip HEAD
```

This includes committed code, documentation, examples, and tests, without Git
history or local caches. Extract the ZIP into a fresh directory and run the
example and test commands above before submitting it.

## Five-minute walkthrough outline

- **0:00–0:40:** Describe the inputs, expected output, and half-open intervals.
- **0:40–2:00:** Explain boundary partitioning and how the rotation index works.
- **2:00–3:00:** Walk through an override crossing a handover, showing why the
  rotation resumes correctly. Show how the CLI calls the pure function.
- **3:00–4:15:** Run the example and tests; explain clipping, timezone decisions,
  and the independent ownership reference.
- **4:15–5:00:** Discuss product extensions: shift swaps with approval, upcoming
  shift reminders, coverage previews, and on-call workload reports.

Record your own explanation and include the video link in the submission notes.
The original assessment brief follows.

---

[job-ad]: https://incident.io/careers#open-roles

## About us

incident.io is the leading AI incident response platform, relied on by some of the best engineering teams in the world when things go wrong.

Since launching in 2021, we've helped over 2,000 companies, including OpenAI, Netflix, and Airbnb, run more than 1 million incidents.

The stakes are real, the talent is insane, and somehow it's a genuinely lovely place to work. We all pull our weight, go the extra mile, and put in the bit of magic most companies don't have time for, all while having fun and never taking ourselves too seriously.

We've raised $96 million from Index Ventures, Insight Partners, and Point Nine, and we're growing fast. There's never been a better time to join.

## What is early careers at incident.io like?

What you need to be successful:
- Have a bias for action and ownership and like to get things shipped, learn from mistakes, and take responsibility for your work.
- Stay curious and don’t just accept things as they are, enjoying asking “why?” and “what if?”
- Collaborate in person and get energy from being around others, bouncing around ideas, asking questions, and giving and receiving feedback.
- Love building whether it’s features, tools, or ideas, and enjoy creating things and seeing them make an impact.
- Enjoy fast-paced environments and feel comfortable with change and the energy that comes with moving quickly.
- Keep a low ego by staying humble and staying focused on the wider mission.

> For more info, check out our [candidate hub](https://incident.io/careers/candidate-hub/early-careers) for a behind-the-scenes look at the life of interns and grads at incident.

## Complete our take-home challenge

### Intro

Imagine you're working at incident.io and we're building a product that can page
(call them, send an SMS, send a notification to a mobile app, etc) engineers
when their services are involved in an incident.

When configuring an on-call system, you don't want to say "whenever service X
goes down, page Y person" as that person probably has a social life and won't
appreciate receiving all the pages, all the time.

Instead, you want to build schedules: a set of people who take it in turns to
provide cover for a service by rotating through on-call shifts.

In JSON form, the configuration that describes how a schedule behaves might look
like this:

```js
// This is a schedule.
{
  "users": [
    "alice",
    "bob",
    "charlie"
  ],

  // 5pm, Friday 6th November 2026
  "handover_start_at": "2026-11-06T17:00:00Z",
  "handover_interval_days": 7
}
```

In that example, our schedule will rotate evenly between those users with the first shift starting at 5pm, 
Friday 6th November 2026, with shift changes happening every 7 days.

That means:

- Alice takes the shift for 1 week, starting at 5pm, Friday 6th November 2026
- Then Bob is on-call for 1 week from 5pm, Friday 13th November 2026
- Then Charlie, then...
- Back to Alice again.

Visually, this might look like this:

![Schedule](./schedule2026.png)

Schedule systems often support 'overrides' where you can add temporary shift
modifications to a schedule, such as if someone wants to go walk their dog or go
to the cinema.

An override specifies the person that will take the shift and the time period it covers.
An example of Charlie covering 5pm–10pm on Monday 9th November 2026 would look like this:

```js
// This is an override.
{
  // Charlie will cover this shift
  "user": "charlie",
  // 5pm, Monday 9th November 2026
  "start_at": "2026-11-09T17:00:00Z",
  // 10pm, Monday 9th November 2026
  "end_at": "2026-11-09T22:00:00Z"
}
```

You can assume that overrides will always be after the schedule's `handover_start_at`, and won't 
overlap with each other.

### Task

We would like you to build – in any language you choose, but ideally one you are
very comfortable in – a script called `./render-schedule` that implements a
scheduling algorithm.

It should be run like so:

```console
$ ./render-schedule \
    --schedule=schedule.json \
    --overrides=overrides.json \
    --from='2026-11-06T17:00:00Z' \
    --until='2026-11-20T17:00:00Z'
[
  {
    "user": "alice",
    "start_at": "2026-11-06T17:00:00Z",
    "end_at": "2026-11-09T17:00:00Z"
  },
  {
    "user": "charlie",
    "start_at": "2026-11-09T17:00:00Z",
    "end_at": "2026-11-09T22:00:00Z"
  },
  {
    "user": "alice",
    "start_at": "2026-11-09T22:00:00Z",
    "end_at": "2026-11-13T17:00:00Z"
  },
  {
    "user": "bob",
    "start_at": "2026-11-13T17:00:00Z",
    "end_at": "2026-11-20T17:00:00Z"
  }
]
```

Where:

- `--schedule` JSON file containing a definition of a schedule (see above example)
- `--overrides` JSON file containing an array of overrides (see above example)
- `--from` the time from which to start listing entries
- `--until` the time until which to list entries

The script should output a JSON array of final schedule as a list of entries.
This should take into account the projected entries (based on the handover
information in the schedule) alongside the provided overrides.

Your schedule should also be truncated based on the from and until parameters provided. 
For example, if an entry was from 1pm November 7 → 1pm November 9, 
but from was 2pm November 8, the entry should be returned as 2pm November 8 → 1pm November 9 
(ignoring the part of the entry that is outside the provided range).

Entries should be truncated to match the from/until parameters.

We care more about correctness than performance: we will only run your code for
time windows up to a few weeks, and with under 100 overrides.

### Code submission and video explanation

We'd like you to submit two things:
1. Your code
2. A 5-minute video walkthrough

Please submit a ZIP file containing the code and a `README.md` that includes 
instructions on running your code, including installation of dependencies.

In the 'notes' field, include a link to a 5-minute video explaining:
- How you approached solving the problem, and why you chose that approach
- How your code implements that solution
- Now you've built the scheduler, what other product features might you build
  on top of this

Imagine you're showing this code to a new team-mate: your video should get
them up-to-speed on the codebase.

(We recommend [Loom](https://www.loom.com) for recording this, but you're welcome 
to use any other tool you're comfortable with).

_You may use AI tools, but you remain responsible for the code you submit. 
You should understand what it does and be able to explain and justify the decisions behind it._
