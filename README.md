# Kaydet — Capture • Query • Remember

<div align="center">
  <img src="logo.png" alt="Kaydet Logo" width="400">
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

## Quick Start

```bash
# Capture a thought
kaydet "Fixed auth bug #work commit:abc123 time:2h status:done"

# Search by metadata
kaydet --search "status:done"
kaydet --search "time:>1"
kaydet --search "commit:abc123"

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

- **Structured metadata**: `key:value` syntax with numeric comparisons (`time:>2`, `status:done`)
- **Smart tagging**: Hashtags (`#work`) and metadata in one natural string
- **Edit/delete by ID**: Stable numeric identifiers for every entry
- **Plain text storage**: Human-readable `.txt` files, one per day
- **SQLite indexing**: Fast search across thousands of entries
- **Browse mode**: Optional TUI with vim-like navigation
- **Git-friendly**: Version your diary, sync across devices
- **MCP integration**: Connect to Claude Desktop and other AI tools

## Usage

### Basic Commands

```bash
# Add an entry
kaydet "Morning standup went well #work"

# Add with metadata
kaydet "Deep work session #focus time:3h intensity:high project:kaydet"

# Search
kaydet --search "#work"
kaydet --search "project:kaydet status:done"
kaydet --search "time:>2"

# Utility
kaydet --tags              # List all tags with counts
kaydet --stats             # Show calendar and stats
kaydet --folder            # Open log directory
kaydet --doctor            # Rebuild index from text files
```

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
```

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

## Use Cases

**Work Logging**
```bash
kaydet "Shipped analytics feature #work commit:a3f89d pr:142 status:done time:4h"
kaydet "Investigating prod timeout #oncall status:wip time:1.5h"
```

**Time Tracking**
```bash
kaydet "Deep work on ETL pipeline #work time:3h focus:high"
kaydet --search "time:>2"  # Find long sessions
```

**Personal Journaling**
```bash
kaydet "Morning run felt amazing #fitness time:30m distance:5k"
kaydet "Read Atomic Habits chapter 3 #reading"
```

**Expense Tracking**
```bash
kaydet "Lunch with client #expense amount:850 currency:TRY billable:yes"
kaydet --search "billable:yes"  # Generate invoice data
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

## Contributing

Bug reports, feature ideas, and pull requests welcome. Open an issue or submit a PR.

## License

MIT License. See [LICENSE](LICENSE) for details.

## Links

- [GitHub Repository](https://github.com/miratcan/kaydet)
- [Blog: Why plain text + SQLite beat every cloud note app](https://mirat.dev/articles/nine-years-of-kaydet/)

---

<div align="center">

Built by [Mirat Can Bayrak](https://github.com/miratcan)

</div>
