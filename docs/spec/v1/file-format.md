# Kaydet File Format Specification

|             |                    |
|-------------|--------------------|
| Version     | 1.0                |
| Status      | Frozen             |
| Date        | 2026-04-15         |

## Overview

Kaydet stores entries in plain text day files. Each file represents a
single day. Files are human-readable and editable with any text editor.

## Encoding

All files MUST be encoded as UTF-8. Implementations SHOULD tolerate
non-UTF-8 bytes by replacing them (lossy decoding) rather than failing.

## Day File

### Naming

Day files MUST be named according to a strftime pattern. The default
pattern is `%Y-%m-%d.txt`, producing filenames like `2026-04-15.txt`.

The pattern is configurable via `DAY_FILE_PATTERN` in the user's config.
Implementations MUST support at least the default pattern.

### Title Block

The first line of a day file is an optional title line, followed by an
optional separator line. These lines are for human readability and MUST
be ignored by parsers (they are not entries).

A title line does NOT match the entry header pattern (it has no `HH:MM`
timestamp prefix).

Example:
```
2026/04/15/ - Tuesday
---------------------
```

The title format is configurable via `DAY_TITLE_PATTERN`. Implementations
MAY generate title blocks but MUST NOT require them for parsing.

## Entry

### Header Line

Every entry begins with a header line matching this pattern:

```
HH:MM [ID]: message | key:value key:value | attachment:name | #tag #tag
```

Formally (regex):
```
^(\d{2}:\d{2})              # timestamp (required)
(?:\s+\[\s*([a-zA-Z0-9]+)\s*\])?  # ID (required for v1)
:\s*(.*)                     # remainder
```

#### Timestamp

- Format: `HH:MM` (24-hour, zero-padded)
- MUST be the first non-whitespace content on the line
- Examples: `09:30`, `14:05`, `00:00`

#### Entry ID

- Format: `[{prefix}{number}]` where prefix is one or more letters
  and number is a positive integer
- Examples: `[d1]`, `[d42]`, `[c7]`, `[s100]`
- The prefix identifies the originating device
- Implementations MUST generate an ID for every new entry
- IDs MUST be unique within a single kaydet instance

#### Remainder

Everything after the `: ` separator is the remainder. It contains,
in order:

1. **Message text** — free-form text, MAY contain inline `#tags`
2. **Metadata section** — zero or more `key:value` pairs, separated
   by the `|` delimiter from the message
3. **Attachment references** — zero or more `attachment:filename` tokens
4. **Explicit tags** — zero or more `#tag` tokens not already in the
   message text

The `|` character is used as a visual delimiter between sections.
Implementations MUST parse tokens regardless of `|` placement —
the delimiter is cosmetic, not structural. Parsing is token-based:

- A token starting with `#` followed by `[a-z][a-z0-9_-]*` is a **tag**
- A token matching `attachment:(.+)` is an **attachment reference**
- A token matching `[a-z][a-z0-9_-]*:.+` is a **metadata pair**
- Everything else is **message text**

### Body Lines

Any lines following a header line, until the next header line or end of
file, are body lines. They are part of the preceding entry.

Body lines MAY have any content including leading whitespace.
Implementations MUST preserve body lines exactly as written (no
trimming, no re-indentation).

An entry with no body lines is valid.

## Tags

### Format

- MUST start with `#` followed by a lowercase letter
- Allowed characters after the first letter: `[a-z0-9_-]`
- Pattern: `#[a-z][a-z0-9_-]*`
- Examples: `#work`, `#project-x`, `#todo`, `#q1_2026`

### Extraction

Tags can appear anywhere in the entry — in the message text, or as
explicit tag markers after metadata. Implementations MUST collect tags
from both locations.

Tags in message text MUST remain in the text (they are not stripped).
Tags are for categorization; the text is the human-readable record.

### Escaping

A backslash before `#` (`\#`) means a literal hash, not a tag.
Implementations MUST NOT extract `\#foo` as a tag.

### Deduplication

Tags MUST be deduplicated (case-insensitive) when stored in the index.
`#Work` and `#work` are the same tag.

## Metadata

### Format

- Key: `[a-z][a-z0-9_-]*` (lowercase, starts with letter)
- Separator: `:` (no spaces around it)
- Value: any non-whitespace string
- Pattern: `key:value`
- Examples: `status:done`, `time:2h`, `commit:a3f8e21`, `amount:150.50`

### Numeric Values

Some metadata values have numeric interpretations:

| Suffix | Interpretation | Example |
|--------|---------------|---------|
| `h`    | hours         | `2h` → 2.0 |
| `m`    | minutes (÷60) | `90m` → 1.5 |
| (none) | raw number    | `150.50` → 150.5 |

Implementations SHOULD store both the string value and numeric value
(when parseable) to support range queries like `time:>2`.

### Reserved Keys

The following metadata keys have special meaning:

| Key             | Purpose |
|-----------------|---------|
| `status`        | Entry status (`pending`, `done`) |
| `completed_at`  | Timestamp when a todo was completed (`HH:MM`) |
| `attachment`    | Reference to an attached file (see Attachments) |

Implementations MUST NOT assign special behavior to other keys.
Users are free to use any key name.

## Attachments

### Storage

Attachments are stored as files in an `attachments/` directory under
STORAGE_DIR:

```
storage/
  2026-04-15.txt
  attachments/
    d1_photo.jpg
    d2_receipt.pdf
```

### Naming Convention

```
{entry_id}_{original_filename}
```

The entry ID prefix links the attachment to its entry. Multiple
attachments per entry are supported.

### Entry Reference

Attachments are referenced in the header line as `attachment:filename`:

```
14:30 [d1]: Park photos #personal | attachment:d1_photo.jpg
```

## Directory Layout

A complete kaydet storage directory:

```
storage/
  2026-04-14.txt           # day files
  2026-04-15.txt
  attachments/             # attached files
    d1_photo.jpg
  secrets/                 # encrypted secrets (see encryption spec)
    d5.enc
```

The SQLite index (`index.db`) is NOT part of the storage directory.
It is a local cache that can be rebuilt from the day files at any time
using `kaydet --doctor`.

## Fixture

See `fixtures/file-format.json` and `fixtures/day-file-simple.txt`
for machine-readable test cases.
