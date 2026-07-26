"""KaydetService unit tests — primary programmatic API (CLI + MCP)."""

from __future__ import annotations

from kaydet import service as service_module


def test_service_add_search_and_delete(service_env):
    service = service_module.KaydetService.initialize()

    result = service.add_entry(
        text="First note #work",
        metadata={"status": "wip"},
        tags=["focus"],
    )
    assert result["success"] is True
    entry_id = result["entry_id"]

    search = service.search_entries("#work")
    assert search["total"] == 1
    match = search["matches"][0]
    assert match["id"] == str(entry_id)
    assert "First note" in match["text"]

    tags = service.list_tags()
    assert {t["tag"] for t in tags["tags"]} == {"focus", "work"}

    delete = service.delete_entry(entry_id)
    assert delete["success"] is True


def test_service_update_and_recent(service_env):
    service = service_module.KaydetService.initialize()

    service.add_entry(text="Morning run #fitness", metadata={"time": "1h"})
    b = service.add_entry(
        text="Lunch with team #work",
        metadata={"mood": "happy"},
    )

    updated = service.update_entry(
        b["entry_id"],
        text="Lunch with team and client #work",
        metadata={"mood": "energized"},
        tags=["team"],
    )
    assert updated["success"] is True

    recent = service.list_recent_entries(limit=2)
    assert len(recent["entries"]) == 2
    ids = [int(entry["id"]) for entry in recent["entries"]]
    assert ids[0] > ids[1]

    by_tag = service.entries_by_tag("team")
    assert len(by_tag["entries"]) == 1
    assert "Lunch with team" in by_tag["entries"][0]["text"]


def test_service_get_stats(service_env):
    service = service_module.KaydetService.initialize()

    service.add_entry(text="Note one")
    service.add_entry(text="Note two")

    stats = service.get_stats()
    assert stats["success"] is True
    assert stats["total_entries"] == 2


def test_service_search_respects_limit(service_env):
    """search_entries default/explicit limit returns truncated flag."""
    service = service_module.KaydetService.initialize()

    for i in range(5):
        service.add_entry(text=f"Note number {i} #batch")

    limited = service.search_entries("#batch", limit=2)
    assert limited["success"] is True
    assert limited["total"] == 5
    assert limited["shown"] == 2
    assert limited["truncated"] is True
    assert len(limited["matches"]) == 2

    unlimited = service.search_entries("#batch", limit=0)
    assert unlimited["total"] == 5
    assert unlimited["shown"] == 5
    assert unlimited["truncated"] is False


def test_service_summarize_entries_with_samples(service_env):
    """summarize_entries must return samples without crashing on date."""
    service = service_module.KaydetService.initialize()

    service.add_entry(
        text="Taxi home #expense",
        metadata={"cost": "120"},
    )
    service.add_entry(
        text="Coffee #expense",
        metadata={"cost": "45"},
    )

    result = service.summarize_entries("#expense")
    assert result["success"] is True
    assert result["total"] == 2
    assert result["sums"]["cost"] == 165
    assert result["sums_display"]["cost"] == "165"  # bare number, no unit
    assert len(result["samples"]) == 2
    sample = result["samples"][0]
    assert sample["date"] == "2025-10-27"
    assert "cost" in sample["metadata"]
    assert sample["id"] is not None
    assert sample["text"]


def test_service_summarize_groups_by_unit_suffix(service_env):
    """Same key + different unit labels are summed separately."""
    service = service_module.KaydetService.initialize()
    service.add_entry(text="A #worklog", metadata={"timespent": "1saat"})
    service.add_entry(text="B #worklog", metadata={"timespent": "2saat"})
    service.add_entry(text="C #worklog", metadata={"timespent": "30dk"})
    service.add_entry(text="D #worklog", metadata={"timespent": "1hour"})
    result = service.summarize_entries("#worklog")
    assert result["success"] is True
    assert result["sums"]["timespent (saat)"] == 3
    assert result["sums_display"]["timespent (saat)"] == "3"
    assert result["sums"]["timespent (dk)"] == 30
    assert result["sums_display"]["timespent (dk)"] == "30"
    assert result["sums"]["timespent (hour)"] == 1
    assert result["sums_display"]["timespent (hour)"] == "1"


def test_service_todo_workflow(service_env):
    """Test creating, listing, and marking todos as done."""
    service = service_module.KaydetService.initialize()

    # Create a todo
    result = service.create_todo(
        description="Write unit tests", metadata={"priority": "high"}
    )
    assert result["success"] is True
    todo_id = result["entry_id"]

    # List todos - should have one pending
    todos = service.list_todos()
    assert todos["success"] is True
    assert len(todos["todos"]) == 1
    assert todos["todos"][0]["id"] == todo_id
    assert todos["todos"][0]["status"] == "pending"
    assert "Write unit tests" in todos["todos"][0]["description"]
    assert "lines" in todos["todos"][0]
    assert "text" in todos["todos"][0]

    # Mark todo as done
    done_result = service.mark_todo_done(todo_id)
    assert done_result["success"] is True

    # List pending todos - should be empty now
    todos_pending = service.list_todos()
    assert len(todos_pending["todos"]) == 0

    # List done todos - should show the completed one
    todos_done = service.list_todos(status="done")
    assert len(todos_done["todos"]) == 1
    assert todos_done["todos"][0]["status"] == "done"
    assert todos_done["todos"][0]["completed_at"] != ""

    # List all todos - should show everything
    todos_all = service.list_todos(status=None)
    assert len(todos_all["todos"]) == 1


def test_service_get_entry(service_env):
    """Test getting a single entry by ID."""
    service = service_module.KaydetService.initialize()

    result = service.add_entry(text="Retrievable note #test")
    entry_id = result["entry_id"]

    # Get by ID
    got = service.get_entry(entry_id)
    assert got["success"] is True
    assert got["entry"]["id"] == str(entry_id)
    assert "Retrievable note" in got["entry"]["text"]

    # Nonexistent ID
    missing = service.get_entry(999999)
    assert missing["success"] is False

    service.delete_entry(entry_id)


def test_service_list_empty_todos(service_env):
    """Test listing todos when there are none."""
    service = service_module.KaydetService.initialize()

    todos = service.list_todos()
    assert todos["success"] is True
    assert todos["todos"] == []


def test_service_create_todo_with_metadata(service_env):
    """Test creating a todo with custom metadata."""
    service = service_module.KaydetService.initialize()

    result = service.create_todo(
        description="Deploy to production",
        metadata={"priority": "critical", "effort": "2h"},
    )
    assert result["success"] is True

    # Verify metadata was saved
    search = service.search_entries("#todo")
    assert search["total"] == 1
    assert "Deploy to production" in search["matches"][0]["text"]


def test_service_suggest_tags_from_file(service_env):
    service = service_module.KaydetService.initialize()
    project_dir = service_env["log_dir"] / "project"
    project_dir.mkdir()
    tags_file = project_dir / ".kaydet.tags"
    tags_file.write_text(
        "# comment line\nwork\nproject-name\n", encoding="utf-8"
    )

    monkeypatch = service_env["monkeypatch"]
    monkeypatch.chdir(project_dir)

    suggestions = service.suggest_tags()
    assert suggestions["success"] is True
    assert suggestions["source"] == "tags_file"
    assert suggestions["suggested_tags"] == ["work", "project-name"]
    assert suggestions["directory"] == str(project_dir)


def test_service_suggest_tags_from_directory_name(service_env):
    service = service_module.KaydetService.initialize()
    project_dir = service_env["log_dir"] / "Feature Space"
    project_dir.mkdir()

    monkeypatch = service_env["monkeypatch"]
    monkeypatch.chdir(project_dir)

    suggestions = service.suggest_tags()
    assert suggestions["success"] is True
    assert suggestions["source"] == "directory_name"
    assert suggestions["suggested_tags"] == ["feature-space"]
    assert suggestions["directory"] == str(project_dir)


def test_suggest_tags_nonexistent_directory(service_env):
    service = service_module.KaydetService.initialize()
    result = service.suggest_tags("/nonexistent/path/xyz")
    assert result["success"] is False
    assert "does not exist" in result["error"]


def test_suggest_tags_file_instead_of_directory(service_env, tmp_path):
    service = service_module.KaydetService.initialize()
    fake_file = tmp_path / "not_a_dir.txt"
    fake_file.write_text("hello")
    result = service.suggest_tags(str(fake_file))
    assert result["success"] is False
    assert "Not a directory" in result["error"]


def test_suggest_tags_empty_tags_file(service_env, tmp_path):
    service = service_module.KaydetService.initialize()
    tags_file = tmp_path / ".kaydet.tags"
    tags_file.write_text("")
    result = service.suggest_tags(str(tmp_path))
    assert result["success"] is True
    assert result["source"] == "directory_name"


def test_suggest_tags_comments_only(service_env, tmp_path):
    service = service_module.KaydetService.initialize()
    tags_file = tmp_path / ".kaydet.tags"
    tags_file.write_text("# this is a comment\n# another comment\n")
    result = service.suggest_tags(str(tmp_path))
    assert result["success"] is True
    assert result["source"] == "directory_name"


def test_suggest_tags_from_file_with_real_tags(service_env, tmp_path):
    service = service_module.KaydetService.initialize()
    tags_file = tmp_path / ".kaydet.tags"
    tags_file.write_text("work\n# comment\nproject-x\n")
    result = service.suggest_tags(str(tmp_path))
    assert result["success"] is True
    assert result["suggested_tags"] == ["work", "project-x"]
    assert result["source"] == "tags_file"



def test_service_doctor_rebuilds_index(service_env):
    service = service_module.KaydetService.initialize()
    service.add_entry(text="Index me #work")
    result = service.doctor()
    assert result["success"] is True
    assert result["total_entries"] >= 1


def test_service_tags_and_list_tags(service_env):
    service = service_module.KaydetService.initialize()
    service.add_entry(text="Tagged #alpha #beta")
    cli_tags = service.tags()
    assert cli_tags["success"] is True
    names = {t["name"] for t in cli_tags["tags"]}
    assert {"alpha", "beta"} <= names

    mcp_tags = service.list_tags()
    assert mcp_tags["success"] is True
    mcp_names = {t["tag"] for t in mcp_tags["tags"]}
    assert {"alpha", "beta"} <= mcp_names


def test_service_git_status_without_repo(service_env):
    service = service_module.KaydetService.initialize()
    result = service.git_status()
    assert result["success"] is False
    assert "Not a git repository" in result["message"]


def test_service_query_returns_entry_objects(service_env):
    service = service_module.KaydetService.initialize()
    service.add_entry(text="Raw query path #q")
    result = service.query("#q")
    assert result["success"] is True
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert hasattr(match, "entry_id")
    assert "Raw query path" in match.text
