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

The header line is the most important part of an entry, containing its timestamp, optional ID, initial message, metadata, and tags.

```
HH:MM [ID]: Message [| metadata:value] [| #tags]
```

-   **`HH:MM` (Required Timestamp):** Represents the hour and minute the entry was created (e.g., `09:30`, `14:05`).
-   **`[ID]` (Optional Entry ID):** A unique numeric identifier for the entry, enclosed in square brackets (e.g., `[123]`). This ID is automatically assigned by `kaydet` but can be manually specified for advanced use cases.
-   **`: ` (Separator):** A colon followed by a space separates the timestamp/ID from the message.
-   **`Message`:** The first line of your diary entry's content. This is typically a brief summary or the start of a longer thought. Tags can also be included directly within the message (e.g., `My #work notes`).
-   **`| metadata:value` (Optional Metadata):** Key-value pairs providing additional structured information about the entry. Multiple metadata items are separated by spaces.
    -   **Format:** `key:value` (e.g., `status:done`, `time:2h`, `priority:high`).
    -   Keys are typically alphanumeric and lowercase.
    -   Values can be any string. `kaydet` can parse numeric values (e.g., `2h` for 2 hours, `90m` for 90 minutes) for advanced search and statistics.
-   **`| #tags` (Optional Hashtags):** Categorical labels for your entry. Multiple tags are separated by spaces. These can appear directly in the `Message` part or in a dedicated segment after a `|` separator.
    -   **Format:** `#tagname` (e.g., `#work`, `#idea`, `#project-x`).
    -   Tags are typically alphanumeric and lowercase.

### Entry Body

Any lines following the header line, until the next entry header or the end of the file, are considered part of the entry's body. These lines can contain free-form text.

## Examples

Here are various examples demonstrating the flexible format:

```
09:00 [1]: Started new project #work #new-project
    Initial setup and planning.
    Need to define scope.

10:30 [2]: Meeting with team | project:alpha status:scheduled
    Discussed progress and next steps.

15:45: Quick break #personal
    Read a chapter of a book.

18:00 [3]: Finished daily report | status:done time:1h #work
    Report submitted to manager.

19:00: Just a simple entry.

20:00: Another entry with metadata only | mood:relaxed
    Enjoying the evening.

21:00: Entry with tags only after separator | #idea #future
    Brainstorming new features.
```

## Parsing Logic

The parsing of these files is handled by the `src/kaydet/parsers.py` module. Key regular expressions used include:
-   `ENTRY_LINE_PATTERN`: For identifying and breaking down entry header lines.
-   `KEY_VALUE_PATTERN`: For extracting metadata key-value pairs.
-   `HASHTAG_PATTERN`: For identifying inline hashtags.

This structured yet flexible format ensures that your diary entries are both human-readable and machine-parsable, enabling powerful search and organization features within `kaydet`.