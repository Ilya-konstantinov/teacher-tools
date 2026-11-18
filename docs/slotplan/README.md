# Slotplan

Slotplan assigns students to arrival slots while accounting for their preferred times, unavailable hours, preparation time, examiner availability, and application deadlines. It maximizes attendance first and resolves competing preferences through exact optimization. A separate command reports examiner workload.

Detailed graph construction, proofs, and complexity analysis are in [ALGORITHM.md](ALGORITHM.md) (Russian).

## Installation

See the [repository guide](../../README.md#installation) for installation and binary builds. Commands below run from the repository root after installation. Use `slotplan` or `python -m slotplan` with your chosen Python interpreter.

## Commands

| Command | Purpose |
| --- | --- |
| `schedule` | Allocate students and write a TSV schedule |
| `workload` | Read a schedule and produce TSV/HTML workload reports |

```sh
slotplan schedule --examiners examples/slotplan/examiners.tsv \
  --students examples/slotplan/students.tsv --output schedule.tsv

slotplan workload --schedule schedule.tsv \
  --examiners examples/slotplan/examiners.tsv --output workload.tsv
```

The workload command also writes `workload.html`. Output directories must already exist. Output paths are relative to the current working directory. Scheduling refuses to overwrite either input table.

The example tables contain fictional names and application timestamps. Replace them with actual data before using a deadline or making real assignments.

## Configuration

Defaults are stored in `config.json` and embedded in the binary:

- `schedule`: `minutes_per_student`, `prep_minutes`, and output filename.
- `workload`: output filename, `warning_ratio`, and workload colors.

Precedence is **explicit CLI argument → user `--config` JSON → project/bundled defaults**. User configuration can contain only the fields being overridden:

```json
{
  "schedule": {"minutes_per_student": 20, "prep_minutes": 40},
  "workload": {"warning_ratio": 0.85}
}
```

```sh
slotplan schedule --config custom.json --examiners examples/slotplan/examiners.tsv \
  --students examples/slotplan/students.tsv
slotplan workload --config custom.json --schedule schedule.tsv \
  --examiners examples/slotplan/examiners.tsv
```

Use the same timing settings for scheduling and workload calculations. If you override examination/preparation time only on the scheduling CLI, also pass the matching `--exam-minutes` / `--prep-minutes` to `workload`. With `--capacity`, the examination duration used for workload is `60 // capacity` minutes.

Unknown fields/sections, wrong types, invalid ranges, and nonfinite numbers are rejected before output. `warning_ratio` must be greater than 0 and at most 1; colors use `#RRGGBB`. The low-level Python `allocate()` function does not read configuration.

## Input tables

Use UTF-8 TSV or CSV. CSV accepts comma or semicolon separators; quote lists of hours when using comma-separated CSV. The first row contains headers. XLSX is not read directly.

Existing Russian student-column labels are part of the input format and must be kept as shown below. Translating this README does not rename those columns. Output column labels and some CLI diagnostics also remain Russian.

### Examiners

Two columns: name and available hours. Header names are arbitrary, as in the provided example. Hour `14` means availability from 14:00 to 15:00. Adjacent available hours form one continuous interval.

```text
ФИО<TAB>Время
Examiner A<TAB>9,10,11
Examiner B<TAB>10,11
```

Replace `<TAB>` with a real tab. An examiner must be available throughout an entire examination; availability cannot switch from one examiner to another in the middle.

### Students

| Required header | Meaning |
| --- | --- |
| `ФИО` | Student name |
| `Группа` | Group, retained as text |
| `Приоритет 1` | First-choice arrival hour |
| `Приоритет 2` | Second-choice arrival hour |
| `Приоритет 3` | Third-choice arrival hour |
| `В какое время вы точно не сможете` | Unavailable hours |

Column order is arbitrary. Preferences and unavailable-hour cells may be empty. Hours can be written as `9` or `9:00`; ranges are not supported. Repeated preferred hours use their best rank. A student's group does not restrict eligible examiners.

Preferences refer to the **arrival hour**. Unavailable hours apply to the student's **entire attendance interval**, from arrival through preparation and examination. Any overlap excludes that slot.

An optional timestamp column can be named `Время заявки` or `Отметка времени`. Accepted formats include `01.11.2026 12:00:00`, `01.11.2026 12:00`, and ISO `2026-11-01 12:00:00`. Dates must use the same timezone. If the column is present, every row must contain a value. Without it, row order defines application order, and `--deadline` cannot be used. Ties in timestamps are broken by row order.

Duplicate examiner names and duplicate student-name/group pairs are errors. Resolve duplicate applications before allocation.

## Timing and capacity

Defaults are 40 minutes of preparation followed by a 30-minute examination. `--prep-minutes` can be 0; `--minutes-per-student` must be between 1 and 60.

Examination duration also determines arrival batch spacing: 30-minute examinations use arrivals at HH:00 and HH:30; 20-minute examinations use HH:00, HH:20, and HH:40. Arrival cannot precede the earliest examiner availability hour.

A batch's capacity is the number of examiners available for the full interval:

```text
[arrival + preparation, arrival + preparation + examination)
```

For example, arrival at 14:30 with 40-minute preparation and a 30-minute examination requires examiner availability from 15:10 to 15:40. Availability at 14:00 alone is insufficient. An examination crossing an hour boundary requires continuous availability across both hours.

There are `60 // minutes_per_student` arrival batches per hour; any remainder is unused. Alternatively, `--capacity N` sets N batches per examiner per hour and derives a duration of `60 // N` minutes. It is mutually exclusive with an explicit `--minutes-per-student`. Individual student durations are not modeled.

The Python `allocate()` API retains a preparation default of 0 for compatibility; pass `prep_minutes=40` explicitly to reproduce CLI defaults.

## Allocation objectives

The solver applies these objectives in strict order:

1. Maximize the total number of assigned students while respecting capacity and availability.
2. Among those solutions, maximize the number of on-time applications assigned.
3. Minimize total preference penalties: first choice 0, second 1, third 2, another allowed hour 3. Late applications receive penalty 3 at every allowed hour; their preferences are ignored.
4. With all preceding objectives tied, choose the best available time for the earliest application, then the next, and so on. Remaining unassigned is worse than any allowed hour.

This is global optimization using minimum-cost maximum flow. Earlier applications cannot reduce the maximum number assigned or worsen the total preference objective. Examiner availability guarantees sufficient continuous capacity, but the output does not assign a named examiner to each student.

### Deadline

```sh
slotplan schedule --examiners examples/slotplan/examiners.tsv \
  --students examples/slotplan/students.tsv --deadline '01.11.2026 12:04:00' \
  --output schedule.tsv
```

The deadline is inclusive: an application received exactly at it is on time. Unavailable hours are respected even for late applications. Preferences remain requests rather than guarantees; assignment to any allowed hour is possible.

## Results and workload

The schedule is a TSV with `Время прихода` (arrival time, HH:MM), `ФИО`, `Группа`, `Приоритет`, and `Причина`, sorted by arrival time and student name. Application timestamps are used internally but not included in the result. An empty priority indicates a time outside the student's preferences or a late application. Unassigned students have an empty arrival time and an explanation; late assignments are marked.

`workload` reads this schedule and examiner availability and produces tabular and HTML reports. It uses the shared timing configuration to account for preparation and examination separately. Its thresholds and colors are configurable. Reports are local files and are not published.

## Development and verification

```sh
python -m unittest discover -s tests/test_slotplan -v
```

Tests cover preferences, deadlines, application order, capacity, duplicate records, unavailable intervals, cross-hour examinations, preparation, reassignment, configuration precedence, and comparisons with exhaustive small-case optima.

| Module | Responsibility |
| --- | --- |
| `src/slotplan/data.py` | Models, table parsing, timestamps, result writing |
| `src/slotplan/allocation.py` | Scheduling optimization |
| `src/slotplan/workload.py` | Workload tables and HTML |
| `src/slotplan/cli.py` | Scheduling command |
| `src/slotplan/config.py` | Configuration loading and validation |

Local real inputs can be kept in `.test/` or `local/`, both ignored by Git. Build outputs live in the repository's ignored `build/` and `dist/` directories.
