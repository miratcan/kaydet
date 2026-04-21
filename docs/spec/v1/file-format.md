# Kaydet File Format Specification

|             |                    |
|-------------|--------------------|
| Version     | 1.1                |
| Status      | Draft              |
| Date        | 2026-04-21         |

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

### Entry Format

Each entry consists of a **header line**, a blank line, the **body**, and a trailing blank line.

```
YYYY-MM-DD HH:MM [ID]:

body text — free-form, may span multiple lines
#tag key:value attachment:filename

```

Two blank lines separate consecutive entries. A blank line MUST follow the header and MUST follow the body.

Example day file:

```
2026-04-21 09:28 [kW3mJ8vq]:

bugün güzel bir gündü #mirat #test

2026-04-21 09:30 [xR7nP2qL]:

toplantı notları #work status:done

```

### Header Line

```
YYYY-MM-DD HH:MM [ID]:
```

Formally (regex):
```
^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+\[([A-Za-z0-9]{8})\]:$
```

#### Date

- Format: `YYYY-MM-DD`
- MUST match the day file name

#### Timestamp

- Format: `HH:MM` (24-hour, zero-padded)
- Examples: `09:30`, `14:05`, `00:00`

#### Entry ID

- Format: 8-character base57 encoded UUID (ShortUUID, first 8 chars)
- Alphabet: `23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz` (no 0, 1, I, O, l)
- Examples: `kW3mJ8vq`, `xR7nP2qL`
- Globally unique — generated from UUID v4, no device prefix needed
- Implementations MUST generate a new ID for every new entry
- IDs MUST be treated as opaque strings — never interpreted as numbers

### Body

Everything after the blank line following the header, until the next blank line.

Body text is free-form and may span multiple lines. Tokens are parsed from the entire body:

- A token matching `#[a-z][a-z0-9_-]*` is a **tag**
- A token matching `attachment:[^\s]+` is an **attachment reference**
- A token matching `[a-z][a-z0-9_-]*:[^\s]+` is a **metadata pair**
- Everything else is **message text**

The `|` character MAY be used as a visual separator but has no structural meaning.

Multi-line bodies are supported:

```
2026-04-21 14:00 [aB3cD4eF]:

sabah koşusu yaptım
5km, 28 dakika
distance:5km time:28m #spor #sağlık

```

### Blank Lines

- One blank line MUST follow the header line
- One blank line MUST follow the body
- Parsers MUST tolerate missing trailing blank lines (EOF)
- Parsers MUST ignore extra blank lines between entries

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
