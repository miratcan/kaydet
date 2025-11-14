# Query Syntax

Kaydet uses a natural, Gmail-like search syntax that's easy to learn and powerful to use.

## Overview

Search queries combine plain text, tags, and metadata filters. All filters are combined with AND logic - entries must match all criteria.

**Basic example:**
```bash
kaydet --filter "#work status:done"
# Finds entries with #work tag AND status:done
```

## Query Elements

### 1. Plain Text Search

Search for words in entry content:

```bash
kaydet --filter "meeting"
# Entries containing "meeting"

kaydet --filter "project update"
# Entries containing both "project" AND "update"
```

**Case insensitive:** `Meeting` = `meeting` = `MEETING`

### 2. Tags

Filter by hashtags using `#`:

```bash
kaydet --filter "#work"
# Entries tagged with #work

kaydet --filter "#work #urgent"
# Entries with both #work AND #urgent
```

### 3. Metadata Filters

Filter by metadata using `key:value` syntax:

#### Exact Match
```bash
kaydet --filter "status:done"
# Entries where status equals "done"

kaydet --filter "project:kaydet"
# Entries where project equals "kaydet"
```

#### Comparison Operators
```bash
kaydet --filter "time:>2"
# time greater than 2

kaydet --filter "time:>=2"
# time greater than or equal to 2

kaydet --filter "miktar:<100"
# miktar less than 100

kaydet --filter "miktar:<=100"
# miktar less than or equal to 100
```

#### Range Queries
```bash
kaydet --filter "time:2..5"
# time between 2 and 5 (inclusive)

kaydet --filter "miktar:100..500"
# miktar between 100 and 500
```

#### Wildcards
```bash
kaydet --filter "project:*"
# Entries that have any project metadata

kaydet --filter "project:kay*"
# project starts with "kay"

kaydet --filter "status:*done"
# status ends with "done"
```

### 4. Exclusion

Exclude results using `-` prefix:

```bash
kaydet --filter "-meeting"
# Entries NOT containing "meeting"

kaydet --filter "-#urgent"
# Entries WITHOUT #urgent tag

kaydet --filter "-status:pending"
# Entries where status is NOT pending
```

### 5. Date Filters

Special metadata for filtering by date:

```bash
kaydet --filter "since:2025-01-01"
# Entries from January 1, 2025 onwards

kaydet --filter "until:2025-12-31"
# Entries up to December 31, 2025

kaydet --filter "since:2025-01-01 until:2025-03-31"
# Entries in Q1 2025

kaydet --filter "since:0"
# All entries (removes default date limit)
```

**Note:** By default, searches are limited to recent entries. Use `since:0` to search all history.

## Examples

### Work & Productivity

**Completed work tasks:**
```bash
kaydet --filter "#work status:done"
```

**Urgent work items still pending:**
```bash
kaydet --filter "#work #urgent status:pending"
```

**Work entries from this month:**
```bash
kaydet --filter "#work since:2025-11-01"
```

**Long meetings (over 2 hours):**
```bash
kaydet --filter "meeting time:>2"
```

### Expenses & Finance

**All expenses:**
```bash
kaydet --filter "#harcama"
```

**Expenses between 100-500 TL:**
```bash
kaydet --filter "#harcama miktar:100..500"
```

**Market expenses this month:**
```bash
kaydet --filter "#harcama #market since:2025-11-01"
```

**Large expenses (over 1000 TL):**
```bash
kaydet --filter "#harcama miktar:>1000"
```

### Todos

**All pending todos:**
```bash
kaydet --filter "#todo status:pending"
```

**Completed todos:**
```bash
kaydet --filter "#todo status:done"
```

**Work-related todos:**
```bash
kaydet --filter "#todo #work"
```

### Projects

**All kaydet project entries:**
```bash
kaydet --filter "project:kaydet"
```

**Any project entries:**
```bash
kaydet --filter "project:*"
```

**Project entries that are done:**
```bash
kaydet --filter "project:* status:done"
```

### Complex Queries

**Work meetings that aren't urgent:**
```bash
kaydet --filter "#work meeting -#urgent"
```

**Completed tasks with time tracking:**
```bash
kaydet --filter "status:done time:>0"
```

**This year's expenses excluding small purchases:**
```bash
kaydet --filter "#harcama since:2025-01-01 miktar:>50"
```

**Personal entries without specific project:**
```bash
kaydet --filter "#personal -project:*"
```

## Tips & Tricks

### 1. Start Simple

Begin with one filter and add more:
```bash
kaydet --filter "#work"              # All work entries
kaydet --filter "#work status:done"  # Add status filter
kaydet --filter "#work status:done time:>2"  # Add time filter
```

### 2. Use Tags for Categories

Tags are faster to type than metadata:
```bash
kaydet --filter "#work"     # Better
kaydet --filter "category:work"  # More typing
```

### 3. Combine Text and Metadata

```bash
kaydet --filter "meeting time:>1"
# Meetings longer than 1 hour

kaydet --filter "Ali project:kaydet"
# Entries mentioning Ali in kaydet project
```

### 4. Finding Missing Metadata

```bash
kaydet --filter "#todo -status:*"
# Todos without status metadata
```

### 5. Date Range for Analysis

```bash
kaydet --filter "#harcama since:2025-01-01 until:2025-01-31"
# January expenses for monthly review
```

## Common Patterns

### Daily Review
```bash
# Today's entries (use --today flag)
kaydet --list --today

# This week's completed tasks
kaydet --filter "status:done since:2025-11-10"
```

### Project Management
```bash
# All project tasks
kaydet --filter "project:myproject"

# Pending project tasks
kaydet --filter "project:myproject status:pending"

# Time spent on project
kaydet --filter "project:myproject time:>0"
```

### Expense Tracking
```bash
# Monthly expenses
kaydet --filter "#harcama since:2025-11-01"

# Expenses by category
kaydet --filter "#harcama #market"
kaydet --filter "#harcama #restaurant"

# Large purchases
kaydet --filter "#harcama miktar:>500"
```

### Time Tracking
```bash
# Entries with time tracking
kaydet --filter "time:>0"

# Long sessions (over 3 hours)
kaydet --filter "time:>3"

# Work time this week
kaydet --filter "#work time:>0 since:2025-11-10"
```

## Limitations

**Current limitations:**
- **No OR logic:** Cannot search for "#work OR #personal" (entries must match all filters)
- **No parentheses:** Cannot group filters like "(#work OR #personal) status:done"
- **AND only:** All filters are combined with AND (this is usually what you want)

**Workarounds:**
- Run multiple searches: `kaydet --filter "#work"` then `kaydet --filter "#personal"`
- Use wildcards: `project:*` matches any project
- Use exclusion: `-#work` excludes work entries

## Related Commands

**List all tags:**
```bash
kaydet --tags
```

**List recent entries:**
```bash
kaydet --list
kaydet --list --today
```

**JSON output for scripting:**
```bash
kaydet --filter "#work" --format json
```

---

**Pro tip:** Kaydet's search syntax is similar to Gmail, macOS Spotlight, and Slack search. If you know those, you already know most of Kaydet's query language!
