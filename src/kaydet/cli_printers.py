import calendar
import json


def print_stats(result, output_format):
    if not result.get("success"):
        if output_format == "json":
            print(json.dumps({"error": result.get("error", "Error")}))
        else:
            print(result.get("error", "Error"))
        return

    if output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(result["month_name"])
        print("Mo Tu We Th Fr Sa Su")
        month_calendar = calendar.Calendar().monthdayscalendar(
            result["year"], result["month"]
        )
        counts = result["days"]
        for week in month_calendar:
            cells = []
            for day in week:
                if day == 0:
                    cells.append("      ")
                    continue
                count = counts.get(day, 0)
                if count == 0:
                    cells.append(f"{day:2d}[  ]")
                elif count < 100:
                    cells.append(f"{day:2d}[{count:2d}]")
                else:
                    cells.append(f"{day:2d}[**]")
            print(" ".join(cells))
        
        total_entries = result["total_entries"]
        if total_entries == 0:
            print("\nNo entries recorded for this month yet.")
        else:
            print(f"\nTotal entries this month: {total_entries}")

def print_tags(result, output_format):
    if not result.get("success"):
        return
    rows = result.get("tags", [])
    if not rows:
        if output_format == "json":
            print(json.dumps({"tags": []}))
        else:
            print("No tags have been recorded yet.")
        return
    
    if output_format == "json":
        print(json.dumps({"tags": rows}, indent=2))
    else:
        for t in rows:
            name, count = t["name"], t["count"]
            label = f"#{name}"
            suffix = "entry" if count == 1 else "entries"
            print(f"{label:<20} {count} {suffix}")

def print_doctor(result):
    if not result.get("success"):
        return
    for msg in result.get("messages", []):
        print(msg)
    total_entries = result.get("total_entries", 0)
    entry_label = "entry" if total_entries == 1 else "entries"
    print(f"Rebuilt search index for {total_entries} {entry_label}.")
    
    tag_stats = result.get("tag_stats", [])
    if tag_stats:
        tag_list = ", ".join(f"#{t['tag']}: {t['count']}" for t in tag_stats)
        print(f"Tags: {tag_list}")
