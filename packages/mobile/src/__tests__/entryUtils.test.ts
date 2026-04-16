import {
  filterEntries,
  formatLastSync,
  groupByDate,
} from "../lib/entryUtils";
import type { EntryData } from "../lib/api";

function makeEntry(overrides: Partial<EntryData> = {}): EntryData {
  return {
    entry_id: "1",
    source_file: "2026-01-01.txt",
    timestamp: "10:00",
    text: "hello world",
    tags: [],
    metadata: {},
    attachments: [],
    updated_at: null,
    ...overrides,
  };
}

// --- filterEntries ---

describe("filterEntries", () => {
  const entries = [
    makeEntry({ entry_id: "1", text: "meeting notes today" }),
    makeEntry({ entry_id: "2", text: "grocery list", tags: ["todo"] }),
    makeEntry({ entry_id: "3", text: "workout log", tags: ["health", "sport"] }),
  ];

  it("returns all entries for empty query", () => {
    expect(filterEntries(entries, "")).toHaveLength(3);
    expect(filterEntries(entries, "  ")).toHaveLength(3);
  });

  it("filters by text content (case insensitive)", () => {
    const result = filterEntries(entries, "Meeting");
    expect(result).toHaveLength(1);
    expect(result[0].entry_id).toBe("1");
  });

  it("filters by tag name", () => {
    const result = filterEntries(entries, "health");
    expect(result).toHaveLength(1);
    expect(result[0].entry_id).toBe("3");
  });

  it("filters by tag with # prefix", () => {
    const result = filterEntries(entries, "#todo");
    expect(result).toHaveLength(1);
    expect(result[0].entry_id).toBe("2");
  });

  it("returns empty array when nothing matches", () => {
    expect(filterEntries(entries, "zzznomatch")).toHaveLength(0);
  });

  it("returns multiple matches", () => {
    const result = filterEntries(entries, "o");
    expect(result.length).toBeGreaterThan(1);
  });
});

// --- groupByDate ---

describe("groupByDate", () => {
  const entries = [
    makeEntry({ entry_id: "1", source_file: "2026-01-02.txt" }),
    makeEntry({ entry_id: "2", source_file: "2026-01-01.txt" }),
    makeEntry({ entry_id: "3", source_file: "2026-01-02.txt" }),
  ];

  it("groups entries by source_file date", () => {
    const sections = groupByDate(entries);
    expect(sections).toHaveLength(2);
  });

  it("sorts sections newest first", () => {
    const sections = groupByDate(entries);
    expect(sections[0].title).toBe("2026-01-02");
    expect(sections[1].title).toBe("2026-01-01");
  });

  it("strips .txt from section title", () => {
    const sections = groupByDate(entries);
    expect(sections[0].title).not.toContain(".txt");
  });

  it("groups all entries for a day together", () => {
    const sections = groupByDate(entries);
    const jan2 = sections.find((s) => s.title === "2026-01-02");
    expect(jan2?.data).toHaveLength(2);
  });

  it("returns empty array for empty input", () => {
    expect(groupByDate([])).toHaveLength(0);
  });
});

// --- formatLastSync ---

describe("formatLastSync", () => {
  it("returns empty string for null", () => {
    expect(formatLastSync(null)).toBe("");
  });

  it("returns 'just now' for < 1 minute ago", () => {
    const d = new Date(Date.now() - 30000);
    expect(formatLastSync(d)).toBe("just now");
  });

  it("returns minutes for < 1 hour", () => {
    const d = new Date(Date.now() - 5 * 60 * 1000);
    expect(formatLastSync(d)).toBe("5m ago");
  });

  it("returns hours for < 1 day", () => {
    const d = new Date(Date.now() - 3 * 60 * 60 * 1000);
    expect(formatLastSync(d)).toBe("3h ago");
  });

  it("returns days for >= 1 day", () => {
    const d = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000);
    expect(formatLastSync(d)).toBe("2d ago");
  });
});
