# Kaydet Diary File Format Specification

`kaydet` stores your diary entries in plain text files, making them easily readable and portable. Each file typically represents a single day's entries, and each entry within a file follows a consistent, human-readable format.

## File Naming Convention

Diary files are named according to the date they represent. The default format is `YYYY-MM-DD.txt`.

**Example:**
- `2025-10-30.txt` for entries made on October 30, 2025.

This pattern can be configured via the `DAY_FILE_PATTERN` setting in your `kaydet` configuration.

## Entry Structure

Each entry within a day file consists of a single header line followed by optional body lines.

### Header Line Format

The header line is the most important part of an entry, containing its timestamp, optional ID, and message with naturally embedded tags and metadata.

```
HH:MM [ID]: Message with #tags and metadata:value
```

-   **`HH:MM` (Required Timestamp):** Represents the hour and minute the entry was created (e.g., `09:30`, `14:05`).
-   **`[ID]` (Optional Entry ID):** A unique numeric identifier for the entry, enclosed in square brackets (e.g., `[123]`). This ID is automatically assigned by `kaydet` but can be manually specified for advanced use cases.
-   **`: ` (Separator):** A colon followed by a space separates the timestamp/ID from the message.
-   **`Message`:** The first line of your diary entry's content. This is written naturally and can include:
    -   **Inline hashtags:** Tags embedded directly in your text (e.g., `Working on #project-x today` or `#meeting notes`)
    -   **Metadata key-value pairs:** Structured information embedded in the text (e.g., `status:done`, `time:2h`, `priority:high`)
-   **`#tags` (Hashtags):** Categorical labels for your entry, written naturally within the message.
    -   **Format:** `#tagname` (e.g., `#work`, `#idea`, `#project-x`).
    -   Tags are typically lowercase alphanumeric with hyphens or underscores.
    -   Tags can appear anywhere in the message text - at the beginning, middle, or end.
-   **`metadata:value` (Metadata):** Key-value pairs providing structured information, embedded naturally in the message.
    -   **Format:** `key:value` (e.g., `status:done`, `time:2h`, `priority:high`).
    -   Keys are lowercase alphanumeric with hyphens or underscores.
    -   Values can be any string. `kaydet` can parse numeric values (e.g., `2h` for 2 hours, `90m` for 90 minutes) for advanced search and statistics.
    -   Metadata is extracted from the message but removed from the displayed text to keep it clean.

### Entry Body

Any lines following the header line, until the next entry header or the end of the file, are considered part of the entry's body. These lines can contain free-form text.

## Examples

Here are various examples demonstrating the natural, flexible format:

```
09:00 [1]: #kaydet projesi icin yeni gelismeler oldu
Initial setup and planning.
Need to define scope.

10:30 [2]: Meeting with team about project:alpha status:scheduled
Discussed progress and next steps.

15:45: Quick break #personal
Read a chapter of a book.

18:00 [3]: Finished daily report status:done time:1h #work
Report submitted to manager.

19:00: Just a simple entry without any tags or metadata.

20:00: Another entry mood:relaxed
Enjoying the evening.

21:00: Brainstorming new features #idea #future
Came up with some interesting concepts.

22:00: Working on #project-alpha and #bugfix today
This entry demonstrates multiple tags naturally embedded.
Tags can appear anywhere in the text flow.

14:00: Need to buy birthday gift #todo status:pending
Remember to check the wishlist.

16:00: Bugun basima neler geldi bilemezsin
#hayat bazen o kadar tahmin edilemez seyler cikariyor ki
insanin karsisina. #blog yazim fikrini not aldim.
```

## Parsing Logic

The parsing of these files is handled by the `src/kaydet/parsers.py` module. Key points:

-   **Entry Detection:** `ENTRY_LINE_PATTERN` identifies entry header lines by timestamp and optional ID.
-   **Tag Extraction:** `HASHTAG_PATTERN` finds `#tagname` patterns anywhere in the entry (header or body lines).
-   **Metadata Extraction:** `KEY_VALUE_PATTERN` identifies `key:value` pairs in the header line and extracts them.
-   **Natural Flow:** Tags remain in the message text for human readability, while metadata is extracted and removed from display.

This natural, flexible format ensures that your diary entries are:
-   **Human-readable:** Write naturally without artificial separators
-   **Machine-parsable:** Tags and metadata are automatically extracted
-   **Search-friendly:** All text, tags, and metadata are indexed for powerful search capabilities