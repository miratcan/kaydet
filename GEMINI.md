# Gemini Added Context

## Project Overview

Kaydet is a command-line interface (CLI) tool designed as a queryable personal database. Its primary purpose is to enable users to quickly capture thoughts, track work, and log daily events directly from their terminal. Key features include:

*   **Plain Text Storage:** Entries are stored in daily plain text files (`~/.local/share/kaydet/YYYY-MM-DD.txt`), ensuring data longevity and compatibility with standard text processing tools like `grep` and `git`.
*   **SQLite Indexing:** A local SQLite database (`index.db`) is used to index entries, facilitating fast full-text search, metadata extraction (e.g., `key:value` pairs), and numeric comparisons (e.g., `time:>2`).
*   **AI Integration (MCP):** Kaydet includes an optional Model Context Protocol (MCP) server, allowing integration with AI assistants like Claude Desktop to query personal data.
*   **Todo Management:** Built-in features for tracking tasks with `--todo`, `--done`, and `--list-todos` commands.
*   **Customizable:** Configuration via `~/.config/kaydet/config.ini` for editor choice, log directory, and color schemes.

The project emphasizes "zero friction" data capture and "AI-ready" personal data management.

## Technologies Used

*   **Language:** Python 3.10+
*   **Database:** SQLite
*   **CLI Framework:** (Inferred from `src/kaydet/cli.py` and usage examples)
*   **Code Formatting/Linting:** Ruff, Black

## Building and Running

### Installation

To install Kaydet with basic functionality:

```bash
pip install git+https://github.com/miratcan/kaydet.git
```

For AI integration with MCP support:

```bash
pip install "git+https://github.com/miratcan/kaydet.git#egg=kaydet[mcp]"
```

### Development Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/miratcan/kaydet.git
    cd kaydet
    ```
2.  **Install in editable mode:**
    ```bash
    pip install -e .
    ```
3.  **Install development dependencies (for testing and linting):**
    ```bash
    pip install -e .[dev]
    ```

### Running Tests

```bash
pytest
```

### Code Style and Linting

```bash
ruff check src
black --check src
```

## Development Conventions

*   **Code Style:** The project adheres to code style enforced by `ruff` and `black`.
*   **Testing:** `pytest` is the chosen framework for unit and integration tests.
*   **Contribution:** Contributions via bug reports, feature ideas, and pull requests are encouraged.
*   **Separation of Concerns:** The project structure (e.g., `cli.py`, `database.py`, `parsers.py`, `commands/`) suggests a focus on separating different functionalities into distinct modules.
*   **Readability:** The `README.md` emphasizes "plain text forever" and "zero friction," implying a preference for clear, maintainable code.
*   **Arrow Anti-Pattern:** The user's memory indicates a strong preference against deeply nested code blocks, suggesting a focus on flat and readable code structures.
