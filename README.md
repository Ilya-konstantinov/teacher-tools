# Teacher Tools

Two command-line tools with importable Python APIs:

- **[Paperforge](docs/paperforge/README.md)** selects distinct question papers, balances difficulty, and renders papers and answers with LaTeX, Typst, or custom renderers.
- **[Slotplan](docs/slotplan/README.md)** schedules students using preferences, preparation time, examiner availability, and deadlines, and reports workload.

## Installation

Requires Python 3.10 or newer. Install from the repository into your chosen Python environment:

```sh
python -m pip install ".[solver]"
paperforge --help
slotplan --help
```

The `solver` extra supplies OR-Tools for CP-SAT algorithms. Install `.` without extras for Slotplan and Paperforge's standard-library algorithms. `python -m paperforge` and `python -m slotplan` are equivalent entry points. The tools use the interpreter you select; they do not discover or activate environments or configure system libraries.

To compile PDFs, install Typst or XeLaTeX/LuaLaTeX separately, together with the fonts required by your template. These are not bundled. Use `--no-pdf` to generate document source without a compiler. See the [rendering guide](docs/paperforge/README.md#document-engines-and-fonts).

## Examples

Run from the repository root:

```sh
mkdir -p outputs
paperforge run --questions examples/paperforge/questions_simple.json \
  -n 2 --tickets 3 --answers --format typst --no-pdf --output outputs/papers.json
slotplan schedule --examiners examples/slotplan/examiners.tsv \
  --students examples/slotplan/students.tsv --output outputs/schedule.tsv
slotplan workload --schedule outputs/schedule.tsv \
  --examiners examples/slotplan/examiners.tsv --output outputs/workload.tsv
```

Examples use demonstration data. Set your own document title, institution, and scheduling options through `--config path/to/config.json`; CLI arguments override configuration. Keep private inputs, machine-specific setup, and generated files outside the source packages, for example in the ignored `local/` and `outputs/` directories.

## Repository structure

```text
src/paperforge/       Paper generation, rendering, default config and templates
src/slotplan/         Scheduling, workload reports and default config
tests/               Unit and integration tests, synthetic fixtures
examples/            Demonstration inputs and renderer
docs/                User guides and algorithm documentation
tools/               Portable binary build and smoke-test scripts
pyproject.toml       Package metadata, dependencies and CLI entry points
```

The two packages have separate namespaces and can be imported in the same process. Package data includes only general defaults and templates. Environment management belongs to the caller.

## Development

```sh
python -m pip install -e ".[solver]"
python -m unittest discover -s tests -v
```

Tests check optimization against exhaustive small cases, input validation, configuration, rendering contracts, failure handling, and CLI execution outside the repository. Tests are not application commands or runtime package data.

## Build standalone executables

```sh
python -m pip install ".[solver,build]"
python tools/build_binaries.py
python tools/smoke_binaries.py --dist-dir dist
```

Use `--project paperforge` or `--project slotplan` to build one tool. The outputs are `dist/paperforge` and `dist/slotplan` (`.exe` on Windows). The binaries bundle Python, application dependencies, general defaults, and Paperforge's Typst templates. They do not bundle PDF compilers or fonts.

Build separately for each OS and architecture. PyInstaller single-file bundles extract to a temporary directory that must permit execution. Linux builds require a compatible system glibc; they are not universal static executables. A manually triggered GitHub Actions workflow builds and smoke-tests Linux, Windows, and macOS outputs.

For Python plugins with extra dependencies, pass `--hidden-import package_name` to the build script, or use an external renderer with its own interpreter. Build outputs are ignored by Git.
