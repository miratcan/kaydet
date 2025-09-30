# Kaydet — Your Thoughts, One Command Away

[![PyPI version](https://img.shields.io/pypi/v/kaydet.svg)](https://pypi.org/project/kaydet/)
[![Downloads](https://img.shields.io/pypi/dm/kaydet.svg)](https://pypi.org/project/kaydet/)
[![Python](https://img.shields.io/pypi/pyversions/kaydet.svg)](https://pypi.org/project/kaydet/)
[![License](https://img.shields.io/github/license/miratcan/kaydet.svg)](LICENSE)

> 🚀 **Ultra-fast command-line diary** | 📦 **Plain text, zero lock-in** | 🏷️ **Smart tagging** | 🤖 **AI-ready**

Kaydet is a lightweight command-line diary that keeps your daily thoughts in
plain text files on your own machine. It is designed to disappear into your
workflow: invoke it for a quick note, drop into your editor for longer
reflections, or pop open the archive folder when you feel nostalgic.

**[📥 Install Now](#installation)** • **[⚡ Quick Start](#quick-start)**

## Demo

<a href="https://asciinema.org/a/Rlcc9GaTQEEfTlUIicvHxm8iC" target="_blank"><img src="https://asciinema.org/a/Rlcc9GaTQEEfTlUIicvHxm8iC.svg" /></a>


## Installation

Install directly from GitHub:

```bash
pip install git+https://github.com/miratcan/kaydet.git
```

For isolated environments, use [pipx](https://github.com/pypa/pipx):

```bash
pipx install git+https://github.com/miratcan/kaydet.git
```

For AI integration, install with MCP support:

```bash
pip install "git+https://github.com/miratcan/kaydet.git#egg=kaydet[mcp]"
```

## Why Kaydet?

### vs. Notion, Obsidian, Logseq
- **🏃 No context switching** — Stay in your terminal, no GUI required
- **⚡ Instant capture** — One command vs. opening an app and navigating menus
- **📂 Plain text files** — No database, no lock-in, grep-able, git-friendly

### vs. Plain Text Files
- **🔍 Built-in search** — Find entries instantly without `grep` wizardry
- **🏷️ Automatic tagging** — Organize with hashtags, auto-archived by tag
- **📊 Stats & insights** — Calendar view, entry counts, activity tracking

### vs. Journaling Apps
- **🔒 Privacy first** — Your data never leaves your machine
- **🎨 Editor freedom** — Use vim, emacs, nano, or any editor you love
- **🔧 Fully customizable** — File naming, timestamps, directory structure

### 🤖 AI-Ready
- **MCP integration** — Works with Claude and other AI assistants out of the box
- **Natural language queries** — "What did I work on last week?" instead of complex searches
- **JSON API** — Structured output for programmatic access and automation
- **Smart summaries** — Let AI analyze patterns and insights from your entries

## Use Cases

Beyond a simple diary, `kaydet`'s combination of fast CLI access, timestamps, and powerful tagging makes it a versatile tool for various logging needs.

### 💼 Work Log
Track tasks, progress, and meeting notes. Use tags to categorize by project or client.

```bash
kaydet "Fixed the authentication bug on the staging server. #project-apollo"
kaydet "Meeting with the design team about the new UI. #meeting #project-apollo"
```

### 📚 Personal Knowledge Base (Today I Learned)
Quickly save new commands, code snippets, or interesting facts you learn.

```bash
kaydet "TIL: `pytest --cov-report=html` generates a browsable coverage report. #python #testing"
```

### 💪 Habit and Fitness Tracker
Log workouts, daily habits, or any other activity you want to track over time.

```bash
kaydet "Completed 5k run in 28 minutes. #fitness #running"
kaydet "Read 20 pages of 'The Pragmatic Programmer'. #habit #reading"
```

### ⏱️ Simple Time Tracking
Log when you start and stop tasks to get a rough idea of time spent.

```bash
kaydet "START: Refactoring the user authentication module. #project-apollo"
kaydet "STOP: Refactoring the user authentication module. #project-apollo"
```

### 💡 Idea Catcher
Instantly capture ideas without breaking your workflow in the terminal.

```bash
kaydet "Idea for a new feature: add encryption for diary files. #kaydet #idea"
```

### 😊 Mood Journal
Quickly log how you're feeling throughout the day. Over time, you can search your `#mood` tags to see patterns.

```bash
kaydet "Feeling productive and focused today. ✨ #mood"
```

### 💰 Simple Expense Tracker
Log business expenses or mileage on the go. The plain text format makes it easy to process later.

```bash
kaydet "Lunch with client: 650.00 TL #expense #client-a"
```

### 🤝 Personal CRM
Keep track of interactions with professional or personal contacts.

```bash
kaydet "Called Ahmet Yılmaz to discuss the proposal. He will follow up by Friday. #ahmet-yılmaz"
```

## Highlights
- **Terminal native** – stays in your shell and respects your configured editor.
- **Own your data** – simple timestamped text files, perfect for syncing however you like.
- **Configurable** – adjust file naming, headings, the editor command, and storage location.
- **Gentle reminders** – optional nudge when you have not written anything for a while.
- **Cross-platform** – works anywhere Python 3.8+ runs.

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

# Quick tag housekeeping
kaydet --folder family   # open
kaydet --tags            # list
kaydet --doctor          # rebuild tag archives

# Search past entries for a word or tag fragment
kaydet --search gratitude
```

Example `kaydet --stats` output:

```
September 2025
Mo Tu We Th Fr Sa Su
 1[  ]  2[  ]  3[  ]  4[  ]  5[  ]  6[  ]  7[  ]
 8[  ]  9[  ] 10[  ] 11[  ] 12[  ] 13[  ] 14[  ]
...
Total entries this month: 12
```

Each entry is written to a daily file (for example `~/.kaydet/2024-02-19.txt`) and
prefixed with the current time. Opening an existing daily file will append a new
section; the first entry of the day creates the file with a heading for easy
navigating.

Add inline hashtags (for example `#family`) to categorize notes — Kaydet keeps
them inline, mirrors the entry into a per-tag folder (for example
`~/.kaydet/family/`), lets you open tag folders directly via `kaydet --folder
family`, shows the tags in `kaydet --tags`, makes them searchable via `kaydet
--search`, and can backfill existing journals with `kaydet --doctor`.

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

## AI Integration (MCP Server)

Kaydet supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), allowing MCP-compatible AI assistants to interact with your diary entries using natural language.

**Supported AI Tools:**
- [Claude Desktop](https://claude.ai/download) - Anthropic's desktop app
- [Cline](https://github.com/cline/cline) - VS Code AI assistant
- [Codex](https://github.com/openai/codex) - OpenAI's code assistant
- Any other MCP-compatible tool

### Installation

```bash
pip install kaydet[mcp]
```

### Configuration

#### For Claude Desktop
Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kaydet": {
      "command": "kaydet-mcp"
    }
  }
}
```

#### For Cline (VS Code)
Add to your Cline MCP settings:

```json
{
  "mcpServers": {
    "kaydet": {
      "command": "kaydet-mcp"
    }
  }
}
```

#### For Other MCP Tools
Refer to your tool's documentation for MCP server configuration. Use `kaydet-mcp` as the command.

### Available Tools

The MCP server exposes these tools to AI assistants:

- **add_entry** - Add new diary entries
- **search_entries** - Search through your diary
- **list_tags** - Get all your tags
- **get_stats** - View entry statistics

### Real-World Use Cases

Once configured, you can interact with your diary using natural language:

#### 📊 **Project Retrospectives**
```
You: "What did I accomplish on the authentication project last month?"

AI: *Searches #auth entries and summarizes*
"You worked on the authentication project 12 times last month:
- Fixed OAuth token refresh bug
- Implemented 2FA
- Migrated to JWT tokens
- Added password reset flow
Most active week was Sept 15-20 with 5 entries."
```

#### 🧠 **Learning Pattern Analysis**
```
You: "What have I learned about Python testing this year?"

AI: *Searches entries tagged #python #testing*
"Based on your TIL entries, you've learned:
- pytest fixtures and parametrization (March)
- Coverage reporting with pytest-cov (June)
- Mocking with unittest.mock (August)
- Property-based testing with Hypothesis (September)"
```

#### 💪 **Fitness Progress Tracking**
```
You: "Am I exercising more this month than last month?"

AI: *Analyzes #fitness entries*
"This month: 18 fitness entries (avg 4.5/week)
Last month: 12 fitness entries (avg 3/week)
You're up 50%! Most consistent activity: running (8 entries)"
```

#### 🎯 **Productivity Insights**
```
You: "What patterns do you see in my work habits?"

AI: *Analyzes #work entries by time and tags*
"Patterns from your work diary:
- Most productive hours: 9-11 AM (highest entry density)
- You tend to do deep work on Tuesdays and Thursdays
- Bug fixes usually happen in the afternoon
- You take breaks more consistently when working on #frontend tasks"
```

#### 💼 **Meeting Follow-ups**
```
You: "What action items came out of meetings with the design team?"

AI: *Searches #meeting #design entries*
"Found 6 design team meetings. Action items mentioned:
- Finalize color palette for dashboard (Sept 5)
- Review mobile mockups (Sept 12)
- Get feedback on new navigation (Sept 19)
- Schedule user testing session (Sept 26 - still pending)"
```

#### 🤝 **Personal CRM**
```
You: "When was my last interaction with John from Marketing?"

AI: *Searches entries mentioning 'John' with #marketing*
"Last contact: September 20
'Quick sync with John from Marketing about Q4 campaign. He'll send
the brief by Friday. Follow up next week. #marketing #john'"
```

#### 💡 **Idea Retrieval**
```
You: "Show me all the feature ideas I've had for Kaydet"

AI: *Searches #kaydet #idea*
"You've logged 8 feature ideas for Kaydet:
- Add encryption for diary files (Sept 2)
- Export to PDF format (Sept 10)
- Mobile companion app (Sept 15)
- Voice-to-text entry (Sept 18)
..."
```

#### ✍️ **Quick Entry via AI**
```
You: "Add diary entry: Finished the user dashboard redesign.
Took longer than expected due to responsive layout issues.
Happy with the final result. #work #frontend #design"

AI: ✅ Entry added to your diary at 14:32
```

### Simple Commands

You can also use simple one-liners:

- "Add a diary entry: Today I fixed the auth bug #work"
- "Search my diary for 'Apollo project'"
- "What are my diary stats for this month?"
- "List all my tags"
- "Show me all my #fitness entries from last week"

### JSON Output

Kaydet also supports JSON output for programmatic access:

```bash
kaydet --search work --format json
kaydet --tags --format json
kaydet --stats --format json
```

## Development
Clone the repository and install in editable mode to hack on Kaydet locally:

```bash
git clone https://github.com/miratcan/kaydet.git
cd kaydet
pip install -e .

# optional: install formatting/lint extras
pip install -e .[dev]

# run style checks
ruff check src
black --check src
```

Run the CLI from source with `python -m kaydet`.

## Contributing

We welcome contributions! Whether it's bug reports, feature requests, or code contributions, please feel free to open an issue or submit a pull request.

## License

Kaydet is released under the permissive [MIT License](LICENSE).

See [CHANGELOG.md](CHANGELOG.md) for release history.

---

<div align="center">

💡 **Found Kaydet useful?**

[⭐ Star the repo](https://github.com/miratcan/kaydet) to help others discover it!

Made with Concerta by [Mirat Can Bayrak](https://github.com/miratcan)

</div>
