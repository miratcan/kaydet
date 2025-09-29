# Kaydet — Your Terminal Diary

Kaydet is a lightweight command-line diary that keeps your daily thoughts in
plain text files on your own machine. It is designed to disappear into your
workflow: invoke it for a quick note, drop into your editor for longer
reflections, or pop open the archive folder when you feel nostalgic.

## Highlights
- **Terminal native** – stays in your shell and respects your configured editor.
- **Own your data** – simple timestamped text files, perfect for syncing however you like.
- **Configurable** – adjust file naming, headings, the editor command, and storage location.
- **Gentle reminders** – optional nudge when you have not written anything for a while.
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

# Add inline hashtags to categorize an entry
kaydet "Dinner with friends #family #gratitude"

# Drop into your favourite editor for a longer note
kaydet --editor

# Open the folder that keeps all diary files
kaydet --folder

# Jump straight to a specific tag folder if it exists
kaydet --folder family
# or with the hashtag form
kaydet --folder #family

# List every tag you've used so far
kaydet --tags

# Search past entries for a word or tag fragment
kaydet --search gratitude

# Entries with hashtags are also copied into per-tag folders
ls ~/.kaydet/family
```

Each entry is written to a daily file (for example `~/.kaydet/2024-02-19.txt`) and
prefixed with the current time. Opening an existing daily file will append a new
section; the first entry of the day creates the file with a heading for easy
navigating.
Add inline hashtags (for example `#family`) to categorize notes — Kaydet moves
them to the end of the entry when saving, mirrors the entry into a per-tag
folder (for example `~/.kaydet/family/`), lets you open tag folders directly via
`kaydet --folder family`, shows the tags in `kaydet --tags`, and makes them
searchable via `kaydet --search`.

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

## Reminders
Want a heads-up if you have not logged anything lately? Add the reminder flag to
your shell startup (for example in `~/.zshrc`):

```bash
# ~/.zshrc
kaydet --reminder
```

When the last entry is older than two hours Kaydet prints:

```
It's been over two hours since your last Kaydet entry. Capture what you've been up to with `kaydet --editor`.
```

If you have written within the last two hours nothing is printed, keeping your
terminal uncluttered.

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
