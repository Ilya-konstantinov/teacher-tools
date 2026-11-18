# Paperforge

Paperforge selects distinct question papers from a question bank and produces printable documents and answer sheets. Papers may contain any valid number of questions. A question cannot repeat within a paper; it may appear in multiple papers. Reordering the same questions does not create a distinct paper.

The selection algorithm is independent of document rendering. Built-in backends produce LaTeX or Typst source. Python functions and external programs can render other formats using the same versioned data contract.

Detailed selection algorithms, proofs, and complexity analysis are in [ALGORITHM.md](ALGORITHM.md) (Russian).

## Installation

See the [repository guide](../../README.md#installation) for installation and binary builds. Commands below run from the repository root after installation. Use `paperforge` or `python -m paperforge` with your chosen Python interpreter.

## Quick start

```sh
paperforge run --questions examples/paperforge/questions_simple.json \
  -n 2 --tickets 3 --answers --format typst --output outputs/papers.json
```

This creates:

```text
outputs/papers.json
outputs/papers.typ
outputs/papers.pdf
outputs/papers_answers.typ
outputs/papers_answers.pdf
```

Use `--no-pdf` to omit compilation. For LaTeX output, use `--format tex` or omit `--format`; source files then use `.tex`. Output directories are created automatically.

| Command | Purpose |
| --- | --- |
| `generate` | Select papers and save JSON |
| `print` | Render existing papers; PDF is opt-in with `--pdf` |
| `answers` | Render questions with their answers; PDF is enabled by default |
| `run` | Generate, render, and compile; add `--answers` to include answers |

```sh
paperforge generate --questions examples/paperforge/questions_simple.json -n 2 --tickets 3 --output papers.json --key-output key.json
paperforge print papers.json --format typst --pdf
paperforge answers papers.json --key key.json --format typst
```

Every command supports `--help`.

## Question bank

The input is a UTF-8 JSON array; a BOM is accepted. A minimal question needs only `text` or `text_file`:

```json
[
  {
    "text": "What is RAII?",
    "group": "Memory",
    "answers": "Resource management tied to object lifetime."
  },
  {
    "text_file": "questions/02.txt",
    "group": "Memory",
    "answers": {
      "correct": ["a", "c"],
      "comment": "Explanation of the correct choices."
    }
  }
]
```

| Field | Meaning |
| --- | --- |
| `text` | Nonempty inline question text |
| `text_file` | Alternative to `text`: a UTF-8 file path |
| `id` | Optional unique nonempty string; generated automatically if omitted |
| `weight` | Positive finite difficulty; either every question specifies it or none does |
| `group` | Nonempty topic name, default `default`; case-sensitive |
| `options` | Optional choice pairs, e.g. `[["a", "First"], ["b", "Second"]]` |
| `answers` | Optional answer text or a `correct`/`comment` object; required for questions included in an answers document |

Without weights, every question receives weight 1. If all weights are equal, the CLI infers the target as `weight × questions-per-ticket`. With differing weights, supply `--target-weight` explicitly. Decimal weights are supported. The algorithm uses `Fraction(str(weight))` internally; JSON floating-point input/output still has ordinary Python float limitations.

`text_file` paths are relative to the bank JSON, with absolute paths and `~` also supported. Do not specify both `text` and `text_file`. A text file contains the question followed optionally by choice lines `a. ...`, `b. ...`; choices can span multiple lines. Explicit JSON `options` override choices read from a file. The output JSON stores the actual text and choices, so later printing does not need the original files.

Automatic IDs are based on array positions (`q1`, `q2`, ...), with suffixes to avoid collisions with explicit IDs. They are reproducible for an unchanged bank, but may change when it is reordered. Use explicit IDs if you need stable external references. Duplicate or invalid explicit IDs are rejected. The input JSON is never rewritten.

You can also pass a directory of `*.txt` files as `--questions`. Files are naturally sorted; filenames become IDs, weights are 1, and all groups are `default`. Answers are not inferred from question text.

Unknown fields are ignored. `section` does not replace `group`. The obsolete `related` field is rejected. The former `answer` spelling is accepted on input; newly written JSON uses `answers`. Conflicting `answer` and `answers` values are rejected.

## Selection and guarantees

Required CLI inputs are `--questions`, `-n` / `--questions-per-ticket`, and `--tickets`. The requested number of distinct papers must fit the available combinations and topic constraints.

| `--group-mode` | Constraint within each paper |
| --- | --- |
| `ignore` | No topic constraint; default |
| `different` | Every question comes from a different topic |
| `same` | All questions come from one topic |

For `different`, choosing as many questions as there are topics gives one question per topic. `same` does not impose quotas across papers.

The default `--objective-mode weight-first` minimizes, in order:

1. Maximum absolute deviation from the target paper weight.
2. Total absolute deviation.

Question frequencies are balanced within interchangeable classes; this is not a global frequency optimum. `optimal=true` proves the two difficulty objectives.

`--objective-mode balanced` instead minimizes maximum deviation, the sum of squared question frequencies, and then total deviation. This retains the original strict global frequency objective.

`--algorithm auto` selects the method. In weight-first mode it tries profile/sum DP, then type selection, then direct CP-SAT as resource limits require. Manual choices are `sum-dp`, `enumerate`, `dp`, `cp-sat-types`, and `cp-sat`. `sum-dp` requires weight-first mode.

| Limit | Default | Scope |
| --- | --- | --- |
| `--max-search-nodes` | 100000 | Type enumeration / plan search budget |
| `--max-dp-states` | 100000 | Stored DP states; transition budget also uses the config multiplier |
| `--time-limit` | 30 seconds | CP-SAT solving stages, not total program wall time |
| `--allow-feasible` | Off | Accept a feasible CP-SAT solution without proving every objective |

Forced algorithms fail when their budgets are exceeded. `auto` may fall back to another exact method. With `--allow-feasible`, an incompletely proven result is explicitly marked `optimal=false`. Different methods can select different papers when objective values tie.

## Generated JSON

The result contains `tickets`, `target_weight`, `max_weight_deviation`, `question_usage`, and `optimization`. Each ticket has a number, total weight, weight deviation, and its question snapshots. Ticket JSON and student renderers omit answers. Add `--key-output key.json` to save the selected answers in a separate file. To render them later, use `paperforge answers tickets.json --key key.json`.

Optimization metadata includes the method, objective mode/count, proven objective prefix, `optimal`, frequency guarantee, class/type counts, and diagnostics such as DP sizes and fallback reasons. `ticket_types` may be `null` when types were not enumerated.

Invalid input or rendering errors are detected before pipeline output is written. PDF compilation occurs after JSON and source output are saved, so a compiler failure leaves those files available for inspection. Successful output paths are overwritten. Writing over known question files, templates, or other pipeline outputs is rejected.

## Answer documents

```sh
paperforge answers papers.json --key key.json --format typst
paperforge answers bank.json --format typst --output bank_answers.typ
```

Generated papers preserve paper numbering and question order. Passing the original bank renders all questions as a single paper. Answers are supplied by the author; Paperforge does not solve questions.

`answers` can be a nonempty string or an object containing `correct` (a list of unique choice labels) and an optional string `comment`. An empty `correct` list means no choices are correct. Unknown labels and missing answers are rejected.

A separate JSON object keyed by question ID remains supported through `answers --key key.json` or `run --answers-key key.json`. That key overrides inline answers and must cover every selected question; unused bank entries are allowed. It is not required when answers are inline.

In a pipeline, `--answers`, `--answers-output`, `--answers-generator`, or `--answers-renderer-command` enables the answers document. `--answers-template` chooses its template separately. Both documents use the selected `--format` and compiler.

## Document engines and fonts

Python package installation does not install external PDF engines:

- **LaTeX:** XeLaTeX (default) or `--engine lualatex`. Built-in output uses `fontspec`, `babel` with Russian support, `geometry`, and the Liberation Serif font. On Debian/Ubuntu, suitable packages include `texlive-xetex`, `texlive-luatex`, `texlive-lang-cyrillic`, and `fonts-liberation`. Custom templates may need additional packages. pdfLaTeX is not supported by the built-in template.
- **Typst:** install the [Typst CLI](https://github.com/typst/typst/releases) and put `typst` on `PATH`. Included templates were tested with 0.14.2 and 0.15.1. Use `--format typst` (alias `typ`); the compiler is inferred automatically.
- **Other formats:** supply a renderer and, for PDF output, a compiler command as described below.

Fonts must be installed on the rendering machine. `--font "DejaVu Serif"` is useful where Liberation Serif is unavailable. Built-in backends treat question text as plain text rather than executable markup. Custom renderers define their own markup policy.

Printing settings include `--tickets-per-page` (1–8, default 4), `--margin-mm` (default 12), `--font-size` (default 12), `--font`, `--title`, and `--institution`. Defaults still contain the original course and institution labels; override them for your course. LaTeX includes cut lines; the default Typst template uses fixed-height paper blocks. Long content does not automatically shrink: reduce papers per page and inspect the resulting PDF. LaTeX overflow/missing-character warnings are reported.

## Custom templates and generators

### Typst templates

```sh
paperforge run --questions bank.json -n 2 --tickets 3 --answers \
  --format typst --template templates/my-papers.typ \
  --answers-template templates/my-answers.typ --output outputs/papers.json
```

Paperforge prepends a `document` variable decoded from embedded JSON, then appends the template. A minimal template is:

```typst
#for ticket in document.tickets [
  = Paper #ticket.ticket
  #for question in ticket.questions [
    #parbreak()#question.text
  ]
]
```

The source is self-contained with respect to question data. Any additional images/imports used by your template must be reachable relative to the generated source and comply with Typst's project-root rules. The built-in templates are in [templates/](../../src/paperforge/templates/). JSON loading follows the [Typst JSON API](https://typst.app/docs/reference/data-loading/json/).

### Versioned renderer contract

All custom renderers receive the same data fields:

```json
{
  "schema_version": 1,
  "mode": "tickets",
  "tickets": [{"ticket": 1, "questions": [{"id": "q1", "text": "Question", "weight": 1, "group": "default", "answers": "Answer"}]}],
  "settings": {"generation": {}, "search": {}, "printing": {}},
  "options": {"title": "Course", "institution": "School", "font_size": 12}
}
```

The illustration abbreviates settings/options; actual values include the resolved configuration and rendering options. Existing generation statistics may also be present. `mode` is `tickets` or `answers`. In answers mode each question additionally has `answer_text`, a validated plain-text representation. Custom student renderers should omit the `answers` fields from their output.

### Python functions

```python
def export_document(data, *, settings, **options):
    # Return nonempty source text; data["mode"] selects papers or answers.
    return "..."
```

```sh
paperforge print papers.json --format html --generator renderer.py:export_document
```

`FILE:function` chooses a function explicitly. With just `FILE`, Paperforge looks for `export_document`, then the legacy `export_tex` / `export_answers_tex` names. In `run`, use independent `--print-generator` and `--answers-generator` options. Python plugins execute inside the process and use its available modules. A frozen binary only contains dependencies collected during its build; use hidden imports at build time or an external renderer for plugins with a different environment.

The existing CppLyc `generate.py` interface (`Question`, `render`, `render_answers`) has a compatibility adapter. Point both generator options to that file; it uses adjacent `template.tex` and `answers-template.tex` unless overridden. Use `--format tex`. Each paper starts on a new page, and question numbering restarts. Its answer renderer expects the structured `correct`/`comment` form, including a nonempty comment. `--date` and `--per-column` are passed to that adapter.

### External programs and arbitrary formats

An external renderer receives UTF-8 contract JSON on stdin and writes only document source to stdout. Diagnostics belong on stderr; a nonzero exit is an error. The program can be written in any language.

```sh
paperforge print papers.json --format html \
  --renderer-command '["python3", "examples/paperforge/render_html.py"]' --output papers.html
```

For `run`, the corresponding options are `--print-renderer-command` and `--answers-renderer-command`. A Python generator and an external renderer cannot both be selected for the same document.

To compile an arbitrary format to PDF, supply a JSON argument array containing `{input}` and `{output}` placeholders:

```sh
paperforge print papers.json --format html \
  --renderer-command '["python3", "examples/paperforge/render_html.py"]' \
  --compiler-command '["weasyprint", "{input}", "{output}"]' --pdf
```

This example requires Python and WeasyPrint in the external environment; they are not Paperforge dependencies. Commands run directly without a shell. Paths containing spaces remain individual arguments. Use absolute script paths in compiler commands because compilation runs in the output directory; renderer commands run in the caller's working directory. A custom compiler must create the requested PDF. Source output must have the extension selected by `--format`; PDF is written beside it.

## Configuration

Configuration precedence is **explicit CLI argument → `--config custom.json` → bundled/project `config.json`**. Custom files can override only the fields they need. Unknown sections/fields, wrong types, nonfinite values, and out-of-range settings are rejected.

- `generation`: group/objective/algorithm defaults, search limits, feasibility policy, output JSON.
- `search`: DP transition multiplier, enumeration threshold, CP-SAT workers, random seed.
- `printing`: layout, font, title, institution.

```json
{
  "generation": {"group_mode": "different", "time_limit": 60},
  "search": {"random_seed": 42},
  "printing": {"title": "C++", "institution": "School", "tickets_per_page": 2}
}
```

Backend selection and external commands are CLI options, not config fields. General input/output paths are relative to the working directory; `text_file` paths are relative to the bank. Multiworker CP-SAT does not guarantee identical tie-breaking from the same seed.

## Python API and development

```python
from pathlib import Path
from paperforge.io import read_questions
from paperforge.planning import plan_tickets
from paperforge.reconstruction import restore_tickets

questions = read_questions(Path("examples/paperforge/questions.json"))
plan = plan_tickets(questions, 2, 3, group_mode="different", target_weight=4)
result = restore_tickets(plan)
```

Planning and reconstruction are separate. `generate_tickets_report()` combines them into `GenerationResult`; `generate_tickets()` returns only the tickets. The Python planning API requires an explicit target weight. Settings can be supplied with `settings=load_settings(path)`. Reconstructing the same plan is reproducible.

Core modules: `planning.py`, `sum_dp.py`, `type_dp.py`, `cp_sat.py`, and `reconstruction.py` implement selection; `io.py` handles banks/snapshots; `documents.py`, `backends.py`, `generators.py`, `printing.py`, and `answers.py` handle rendering and compilation.

Run `python -m unittest discover -s tests/test_paperforge -v`. Tests compare solvers with exhaustive small cases, verify constraints and reconstruction, and cover file-backed questions, optional IDs, inline answers, configuration, renderer contracts, error propagation, and output collisions. Binary smoke tests live in [tools/](../../tools/).

### Hand off selected papers to another program

    paperforge generate bank.json -n 2 -t 3 --then python3 my_renderer.py

Paperforge writes the selected papers and appends the absolute JSON path to the command arguments. The program inherits the working directory and terminal and controls all its outputs. A nonzero exit status fails the command and leaves the tickets available for retry.

A question can specify `"answer_file": "answers/q1.txt"` instead of inline `answers`. Paths resolve relative to the bank just like `text_file`. UTF-8 text is preserved, including line breaks. A file ending in `.json` contains an answer string or a structured answer object. Answer renderers receive the loaded value in `answers`. Student renderers and the JSON passed to `--then` receive only the questions and ticket metadata.
