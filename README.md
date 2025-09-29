# Kaydet — Your Terminal Diary

Kaydet is a lightweight command-line diary that keeps your daily thoughts in
plain text files on your own machine. It is designed to disappear into your
workflow: invoke it for a quick note, drop into your editor for longer
reflections, or pop open the archive folder when you feel nostalgic.

## Highlights
- **Terminal native** – stays in your shell and respects your configured editor.
- **Own your data** – simple timestamped text files, perfect for syncing however you like.
- **Configurable** – adjust file naming, headings, the editor command, and storage location.
- **Cross-platform** – works anywhere Python 3.8+ runs.

## Installation
Kaydet is published on PyPI and installs like any other Python CLI:

```bash
pip install kaydet
```

Prefer isolated environments? Kaydet also works well with [pipx](https://github.com/pypa/pipx):

```bash
pipx install kaydet
```

## Quick Start
```bash
# Append a short entry to today's file
kaydet "Made progress on the side project."

# Drop into your favourite editor for a longer note
kaydet --editor

# Open the folder that keeps all diary files
kaydet --folder
```

Each entry is written to a daily file (for example `~/.kaydet/2024-02-19.txt`) and
prefixed with the current time. Opening an existing daily file will append a new
section; the first entry of the day creates the file with a heading for easy
navigating.

## Configuration
Kaydet stores its settings in `~/.config/kaydet/config.ini` (or the location
pointed to by `XDG_CONFIG_HOME`). The file is created on first run and you can
change any of the values. A minimal example:

```ini
[SETTINGS]
DAY_FILE_PATTERN = %Y-%m-%d.txt
DAY_TITLE_PATTERN = %Y/%m/%d - %A
LOG_DIR = /Users/you/.kaydet
EDITOR = nvim
```

- `DAY_FILE_PATTERN` controls the diary file name.
- `DAY_TITLE_PATTERN` sets the heading written at the top of new files.
- `LOG_DIR` points to the directory where entries live.
- `EDITOR` is the command Kaydet runs for long-form entries (`--editor`).

Any edits take effect the next time you invoke Kaydet.

## Development
Clone the repository and install in editable mode to hack on Kaydet locally:

```bash
git clone https://github.com/miratcan/kaydet.git
cd kaydet
pip install -e .
```

Run the CLI from source with `python -m kaydet`.

## License
Kaydet is released under the permissive [MIT License](LICENSE).
