import type { EntryData } from "./api";

export interface Section {
  title: string;
  data: EntryData[];
}

function formatSectionDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today.getTime() - date.getTime()) / 86400000);

  const dayName = date.toLocaleDateString("en-US", { weekday: "long" });
  const monthName = date.toLocaleDateString("en-US", { month: "short" });
  const formatted = `${d} ${monthName} ${y}`;

  let relative: string;
  if (diffDays === 0) relative = "Today";
  else if (diffDays === 1) relative = "Yesterday";
  else if (diffDays > 0) relative = `${diffDays} Days Ago`;
  else relative = `In ${-diffDays} Days`;

  return `${formatted} (${dayName}, ${relative})`;
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
    .map(([key, data]) => ({ title: formatSectionDate(key), data }));
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
