# Kaydet — Capture • Query • Remember

<div align="center">
  <img src="assets/logo.png" alt="Kaydet Logo" width="400">
  <br><br>
</div>

[![Tests](https://github.com/miratcan/kaydet/workflows/Tests/badge.svg)](https://github.com/miratcan/kaydet/actions)
[![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen.svg)](https://github.com/miratcan/kaydet/actions/workflows/test.yml)
[![License](https://img.shields.io/github/license/miratcan/kaydet.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Maintained](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/miratcan/kaydet/graphs/commit-activity)
[![GitHub stars](https://img.shields.io/github/stars/miratcan/kaydet?style=social)](https://github.com/miratcan/kaydet/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/miratcan/kaydet)](https://github.com/miratcan/kaydet/commits/master)

> Your queryable personal database. Plain text storage, SQLite search, zero friction.

Kaydet is not a diary you read—it's a database you query. Capture thoughts, track work, log life—all from your terminal, in plain text.

## Install

```bash
pip install git+https://github.com/miratcan/kaydet.git
```

Or with MCP support for AI integration:

```bash
pip install "git+https://github.com/miratcan/kaydet.git#egg=kaydet[mcp]"
```

> The `kaydet-mcp` entry point stays installed, but it only becomes usable
> after installing this optional `mcp` extra.

## Quick Start

```bash
# Capture a thought
kaydet "Fixed auth bug #work commit:abc123 time:2h status:done"

# Search by metadata
kaydet --filter "status:done"
kaydet --filter "time:>1"
kaydet --filter "commit:abc123"

# List all tags
kaydet --tags

# Open in editor
kaydet --editor

# Edit or delete by ID
kaydet --edit 42
kaydet --delete 42
```

## Why Kaydet?

**Zero Friction**
One command from your terminal. No app windows, no context switching, no loading screens.

**Plain Text Forever**
Daily `.txt` files you can grep, version with git, sync however you like. No proprietary formats, no lock-in.

**Queryable Database**
SQLite index with full-text search, metadata extraction, and numeric comparisons. Search `time:>2` to find long work sessions.

**AI-Ready**
Built-in MCP server exposes your archive to Claude Desktop. Ask your AI about your own life.

## Features

- **Todo management**: Built-in task tracking with `--todo`, `--done`, and `--list-todos` commands
- **Structured metadata**: `key:value` syntax with numeric comparisons (`time:>2`, `status:done`)
- **Smart tagging**: Hashtags (`#work`) and metadata in one natural string
- **Edit/delete by ID**: Stable numeric identifiers for every entry
- **Plain text storage**: Human-readable `.txt` files, one per day
- **SQLite indexing**: Fast search across thousands of entries
- **Git-friendly**: Version your diary, sync across devices
- **MCP integration**: Connect to Claude Desktop and other AI tools with todo support
- **Built-in sync**: Push/pull sync between devices via HTTP or stdin, with encrypted secrets and attachment sync
- **File attachments**: Attach files to entries with `--attach` and `--grab`

## Usage

### Basic Commands

```bash
# Add an entry
kaydet "Morning standup went well #work"

# Add with metadata
kaydet "Deep work session #focus time:3h intensity:high project:kaydet"

# Search
kaydet --filter "#work"
kaydet --filter "project:kaydet status:done"
kaydet --filter "time:>2"

# Todo Management
kaydet --todo "Write unit tests priority:high"
kaydet --done 42           # Mark todo as done
kaydet --list-todos        # List all todos
kaydet --todo              # List todos (shorthand)

# Utility
kaydet --tags              # List all tags with counts
kaydet --stats             # Show calendar and stats
kaydet --folder            # Open log directory
kaydet --doctor            # Rebuild index from text files
```

> Need a literal `#` in your note? Escape it as `\#` (e.g.,
> `kaydet "Budget was \#1"`).

### Entry Format

Entries are stored as plain text with this format:

```
14:25 [42]: Fixed auth bug | commit:abc123 time:2h status:done | #work #urgent
```

- Timestamp and unique ID
- Message
- Metadata (`key:value` pairs)
- Tags (hashtags)

### File Structure

```
~/.local/share/kaydet/
├── 2025-10-26.txt
├── 2025-10-27.txt
├── 2025-10-28.txt
└── index.db  (SQLite cache)
```

### Metadata Queries

Kaydet parses `key:value` pairs and supports:

- **Exact match**: `status:done`, `project:kaydet`
- **Numeric comparison**: `time:>2`, `time:>=1.5`, `time:<5`
- **Ranges**: `time:1..3` (between 1 and 3 hours)
- **Duration parsing**: `2h` → `2.0`, `90m` → `1.5`, `2.5h` → `2.5`

### Configuration

Settings are in `~/.config/kaydet/config.ini`:

```ini
[SETTINGS]
DAY_FILE_PATTERN = %Y-%m-%d.txt
DAY_TITLE_PATTERN = %Y/%m/%d - %A
LOG_DIR = ~/.local/share/kaydet
EDITOR = nvim
REMIND_AFTER_HOURS = 4
COLOR_HEADER = bold cyan
COLOR_TAG = bold magenta
COLOR_DATE = green
COLOR_ID = yellow
```

If `STORAGE_DIR` is omitted, Kaydet picks a sensible default on first run:
- macOS / Windows → `~/Documents/Kaydet`
- Linux → `~/Kaydet`
Prefer hidden/XDG dirs? Change `STORAGE_DIR` (e.g., `~/.local/share/kaydet`) in
`config.ini` and rerun `kaydet --config`; the CLI offers to move files for you.

### Color Customization

You can customize the colors of various elements in the output by adding the following settings under the `[SETTINGS]` section in `config.ini`:

```ini
[SETTINGS]
# ... existing settings ...
COLOR_HEADER = bold cyan
COLOR_TAG = bold magenta
COLOR_DATE = green
COLOR_ID = yellow
```

- `COLOR_HEADER`: Color for date separators and section headers.
- `COLOR_TAG`: Color for tags (e.g., `#work`).
- `COLOR_DATE`: Color for timestamps in search results.
- `COLOR_ID`: Color for entry IDs and pending todo counts.

You can use any [Rich color string](https://rich.readthedocs.io/en/stable/style.html#color-names) (e.g., `red`, `bold green`, `rgb(255,100,0)`).

## AI Integration

Connect Kaydet to Claude Desktop via MCP:

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "kaydet": {
      "command": "kaydet-mcp"
    }
  }
}
```

Then ask Claude:
- "What did I work on this week?"
- "How consistent was my fitness routine last month?"
- "Summarize my accomplishments from last sprint"

Your AI assistant with perfect memory of your own data.

### MCP Tools

- `suggest_kaydet_tags` – Suggest tags for assistants by reading `.kaydet.tags` in
  the current project or falling back to the directory name when no override is
  defined.

## Use Cases

**Work Logging**
```bash
kaydet "Shipped analytics feature #work commit:a3f89d pr:142 status:done time:4h"
kaydet "Investigating prod timeout #oncall status:wip time:1.5h"
```

**Time Tracking**
```bash
kaydet "Deep work on ETL pipeline #work time:3h focus:high"
kaydet --filter "time:>2"  # Find long sessions
```

**Personal Journaling**
```bash
kaydet "Morning run felt amazing #fitness time:30m distance:5k"
kaydet "Read Atomic Habits chapter 3 #reading"
```

**Expense Tracking**
```bash
kaydet "Lunch with client #expense amount:850 currency:TRY billable:yes"
kaydet --filter "billable:yes"  # Generate invoice data
```

## Development

```bash
git clone https://github.com/miratcan/kaydet.git
cd kaydet
pip install -e .
```

Run tests:
```bash
pip install -e .[dev]
pytest
ruff check src
```

## Sync

Kaydet has built-in sync — no third-party cloud services needed.

### Setup

**On your server:**
```bash
kaydet server generate-key --name "my-laptop"
# → kyd_a1b2c3d4e5f6...

kaydet server start --transport http --host 0.0.0.0
# → Sync server listening on 0.0.0.0:8484
```

**On your client:**
```bash
kaydet sync setup
# Choose: http
# Server URL: https://my-server.example.com:8484
# API key: kyd_a1b2c3d4e5f6...

kaydet sync
# → Pushed 3 entries, Pulled 1 entry
```

### How it works

- Server is a full kaydet instance with its own storage
- Every device keeps a complete local copy
- Changes are tracked via an append-only log (`sync_log`)
- Conflicts resolved automatically (last-writer-wins)
- Encrypted secrets sync as opaque blobs — server can't read them
- Attachments sync separately via base64 transport

### Alternative: folder sync

If you prefer not to run a server, you can still sync the plain text
files via any folder sync tool (Syncthing, Resilio, etc.). Each device
builds its own search index locally.

```
~/Documents/Kaydet/        → Synced folder
  ├── 2025-01-15.txt
  └── 2025-01-16.txt

~/.local/share/kaydet/     → Local only
  └── index.db
```

## Contributing

Bug reports, feature ideas, and pull requests welcome. Open an issue or submit a PR.
See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines and the full philosophy.

## License

MIT License. See [LICENSE](LICENSE) for details.

## Links

- [GitHub Repository](https://github.com/miratcan/kaydet)
- [Blog: Why plain text + SQLite beat every cloud note app](https://mirat.dev/articles/nine-years-of-kaydet/)
- [Sync Protocol](docs/SYNC_PROTOCOL.md) — sync protocol specification
- [docs/AGENTS.md](docs/AGENTS.md) — agents must read this before interacting with the repo

---

<div align="center">

Built by [Mirat Can Bayrak](https://github.com/miratcan)

</div>
