import type { EntryData } from "./api";

export interface Section {
  title: string;
  data: EntryData[];
}

export function groupByDate(entries: EntryData[]): Section[] {
  const groups = new Map<string, EntryData[]>();
  for (const entry of entries) {
    const day = entry.source_file.replace(/\.txt$/, "");
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day)!.push(entry);
  }
  return [...groups.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([title, data]) => ({ title, data }));
}

export function filterEntries(
  entries: EntryData[],
  query: string
): EntryData[] {
  const q = query.trim().toLowerCase();
  if (!q) return entries;
  return entries.filter((e) => {
    if (e.text.toLowerCase().includes(q)) return true;
    if (
      e.tags.some((t) =>
        t.toLowerCase().includes(q.replace(/^#/, ""))
      )
    )
      return true;
    return false;
  });
}

export function formatLastSync(date: Date | null): string {
  if (!date) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return `${Math.floor(diffH / 24)}d ago`;
}
