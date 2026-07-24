from datetime import date
from pathlib import Path

from kaydet.parsers import (
    _parse_base_token,
    build_numeric_metadata,
    count_entries,
    deduplicate_tags,
    extract_tags_from_text,
    extract_words_from_text,
    format_entry_header,
    normalize_tag,
    parse_comparison_expression,
    parse_day_entries,
    parse_metadata_token,
    parse_numeric_value,
    parse_range_expression,
    parse_stored_entry_remainder,
    partition_entry_tokens,
    resolve_entry_date,
    tokenize,
    tokenize_query,
    tokenize_query_terms,
)

# --- tokenize_query_terms ---

def test_tokenize_query_terms_empty():
    assert tokenize_query_terms("") == []


def test_tokenize_query_terms_splits_by_whitespace():
    assert tokenize_query_terms('a b c') == ['a', 'b', 'c']


def test_tokenize_query_terms_respects_quotes():
    expected = ["hello world", "#tag"]
    assert tokenize_query_terms('"hello world" #tag') == expected


# --- _parse_base_token ---

def test_parse_base_token_word():
    t = _parse_base_token("hello")
    assert t.type == "WORD"
    assert t.value == "hello"


def test_parse_base_token_url():
    t = _parse_base_token("https://example.com")
    assert t.type == "WORD"


def test_parse_base_token_tag():
    t = _parse_base_token("#work")
    assert t.type == "TAG"
    assert t.value == "work"


def test_parse_base_token_metadata():
    t = _parse_base_token("time:2h")
    assert t.type == "METADATA"
    assert t.value == ("time", "2h")


# --- tokenize ---

def test_tokenize_basic():
    tokens = tokenize("#work time:>1")
    assert tokens[0].type == "TAG"
    assert tokens[0].value == "work"
    assert tokens[1].type == "METADATA"
    assert tokens[1].value == ("time", ">1")


def test_tokenize_exclusion():
    tokens = tokenize("-word -#personal -status:done hello")
    assert tokens[0].type == "EXCLUDE_WORD"
    assert tokens[0].value == "word"
    assert tokens[1].type == "EXCLUDE_TAG"
    assert tokens[1].value == "personal"
    assert tokens[2].type == "EXCLUDE_METADATA"
    assert tokens[3].type == "WORD"
    assert tokens[3].value == "hello"


# --- normalize_tag ---

def test_normalize_tag_strips_hash():
    assert normalize_tag("#Work") == "work"


def test_normalize_tag_already_clean():
    assert normalize_tag("work") == "work"


def test_normalize_tag_invalid():
    assert normalize_tag("123") is None


# --- parse_metadata_token ---

def test_parse_metadata_token_basic():
    assert parse_metadata_token("status:done") == ("status", "done")


def test_parse_metadata_token_invalid():
    assert parse_metadata_token("notmetadata") is None


def test_parse_metadata_token_empty_value():
    assert parse_metadata_token("key:") is None


def test_parse_metadata_token_url_like():
    assert parse_metadata_token("key://value") is None


# --- parse_numeric_value ---

def test_parse_numeric_value_hours():
    assert parse_numeric_value("3h") == 3.0


def test_parse_numeric_value_minutes():
    assert parse_numeric_value("30m") == 0.5


def test_parse_numeric_value_saat():
    assert parse_numeric_value("3saat") == 3.0


def test_parse_numeric_value_dk():
    assert parse_numeric_value("30dk") == 0.5


def test_parse_numeric_value_plain():
    assert parse_numeric_value("42") == 42.0


def test_parse_numeric_value_non_numeric():
    assert parse_numeric_value("abc") is None


def test_parse_numeric_value_empty():
    assert parse_numeric_value("") is None


# --- build_numeric_metadata ---

def test_build_numeric_metadata():
    result = build_numeric_metadata({"time": "2h", "priority": "high"})
    assert result == {"time": 2.0}


def test_build_numeric_metadata_empty():
    assert build_numeric_metadata({}) == {}


# --- partition_entry_tokens ---

def test_partition_entry_tokens():
    msg, meta, tags = partition_entry_tokens(["work on #kaydet time:3h"])
    assert tags == ["kaydet"]
    assert meta == {"time": "3h"}
    assert "work on" in msg[0]


def test_partition_entry_tokens_escaped_hash():
    msg, meta, tags = partition_entry_tokens([r"Note about \#notatag #work"])
    assert msg[0] == "Note about #notatag"
    assert tags == ["work"]


# --- format_entry_header ---

def test_format_entry_header_basic():
    result = format_entry_header("14:30", "meeting", {}, [])
    assert result == "14:30: meeting"


def test_format_entry_header_with_id():
    result = format_entry_header("14:30", "meeting", {}, [], entry_id="42")
    assert result == "14:30 [42]: meeting"


def test_format_entry_header_with_metadata():
    result = format_entry_header("14:30", "deploy", {"status": "done"}, [])
    assert result == "14:30: deploy status:done"


def test_format_entry_header_with_tags():
    result = format_entry_header("09:00", "standup", {}, ["work"])
    assert result == "09:00: standup #work"


def test_format_entry_header_with_attachments():
    result = format_entry_header(
        "10:00", "notes", {}, [], attachments=["doc.pdf"]
    )
    assert result == "10:00: notes attachment:doc.pdf"


def test_format_entry_header_no_message():
    result = format_entry_header("12:00", "", {}, [])
    assert result == "12:00:"


# --- parse_stored_entry_remainder ---

def test_parse_stored_entry_remainder_basic():
    msg, meta, tags, attachments = parse_stored_entry_remainder(
        "fixed bug status:done #work"
    )
    assert "fixed bug" in msg
    assert meta == {"status": "done"}
    assert tags == ["work"]


def test_parse_stored_entry_remainder_with_attachment():
    msg, meta, tags, attachments = parse_stored_entry_remainder(
        "screenshot attachment:img.png"
    )
    assert attachments == ["img.png"]


def test_parse_stored_entry_remainder_empty():
    msg, meta, tags, attachments = parse_stored_entry_remainder("")
    assert msg == ""
    assert meta == {}
    assert tags == []
    assert attachments == []


# --- tokenize_query ---

def test_tokenize_query_empty():
    text, ex_text, meta, ex_meta, tags, ex_tags = tokenize_query("")
    assert all(x == [] for x in (text, ex_text, meta, ex_meta, tags, ex_tags))


def test_tokenize_query_all_types():
    text, ex_text, meta, ex_meta, tags, ex_tags = tokenize_query(
        "hello -world #work -#personal status:done -priority:high"
    )
    assert text == ["hello"]
    assert ex_text == ["world"]
    assert tags == ["work"]
    assert ex_tags == ["personal"]
    assert meta == [("status", "done")]
    assert ex_meta == [("priority", "high")]


# --- parse_range_expression ---

def test_parse_range_basic():
    assert parse_range_expression("1..3") == (1.0, 3.0)


def test_parse_range_open_start():
    assert parse_range_expression("..5") == (None, 5.0)


def test_parse_range_open_end():
    assert parse_range_expression("2..") == (2.0, None)


def test_parse_range_not_a_range():
    assert parse_range_expression("hello") is None


# --- parse_comparison_expression ---

def test_parse_comparison_gte():
    assert parse_comparison_expression(">=2") == (">=", 2.0)


def test_parse_comparison_lt():
    assert parse_comparison_expression("<5") == ("<", 5.0)


def test_parse_comparison_lte():
    assert parse_comparison_expression("<=10") == ("<=", 10.0)


def test_parse_comparison_gt():
    assert parse_comparison_expression(">1") == (">", 1.0)


def test_parse_comparison_not_comparison():
    assert parse_comparison_expression("hello") is None


# --- parse_day_entries ---

def test_parse_day_entries_basic(tmp_path):
    day_file = tmp_path / "2024-01-15.txt"
    day_file.write_text(
        "14:30 [1]: first entry #work\n"
        "15:00 [2]: second entry #personal status:done\n"
    )
    entries = parse_day_entries(day_file, date(2024, 1, 15))
    assert len(entries) == 2
    assert entries[0].entry_id == "1"
    assert entries[0].timestamp == "14:30"
    assert entries[1].tags == ("personal",)
    assert entries[1].metadata == {"status": "done"}


def test_parse_day_entries_multiline(tmp_path):
    day_file = tmp_path / "2024-06-01.txt"
    day_file.write_text(
        "10:00 [1]: notes\n"
        "  continued on next line\n"
        "  and another\n"
    )
    entries = parse_day_entries(day_file, date(2024, 6, 1))
    assert len(entries) == 1
    assert len(entries[0].lines) == 3


def test_parse_day_entries_legacy_tags(tmp_path):
    day_file = tmp_path / "2023-01-01.txt"
    day_file.write_text("09:00: [work,dev] started project\n")
    entries = parse_day_entries(day_file, date(2023, 1, 1))
    assert len(entries) == 1
    assert entries[0].tags == ("work", "dev")


def test_parse_day_entries_empty_file(tmp_path):
    day_file = tmp_path / "empty.txt"
    day_file.write_text("")
    assert parse_day_entries(day_file, date(2024, 1, 1)) == []


def test_parse_day_entries_no_entries(tmp_path):
    day_file = tmp_path / "noise.txt"
    day_file.write_text("just some random text\nno timestamps here\n")
    assert parse_day_entries(day_file, date(2024, 1, 1)) == []


# --- deduplicate_tags ---

def test_deduplicate_tags():
    assert deduplicate_tags(["dev", "work", "dev"], []) == ("dev", "work")


def test_deduplicate_tags_from_lines():
    result = deduplicate_tags(["work"], ["some text #dev here"])
    assert "dev" in result
    assert result.index("work") < result.index("dev")


def test_deduplicate_tags_case_insensitive():
    assert deduplicate_tags(["Work"], []) == ("work",)


# --- extract_tags_from_text ---

def test_extract_tags_from_text():
    assert extract_tags_from_text("#hello #world") == ("hello", "world")


def test_extract_tags_from_text_empty():
    assert extract_tags_from_text("") == ()


def test_extract_tags_from_text_no_tags():
    assert extract_tags_from_text("plain text") == ()


# --- extract_words_from_text ---

def test_extract_words_from_text():
    assert extract_words_from_text("Hello, World!") == ["hello", "world"]


def test_extract_words_from_text_empty():
    assert extract_words_from_text("") == []


# --- count_entries ---

def test_count_entries(tmp_path):
    day_file = tmp_path / "diary.txt"
    day_file.write_text("14:30: first\nrandom line\n15:00: second\n")
    assert count_entries(day_file) == 2


def test_count_entries_no_entries(tmp_path):
    day_file = tmp_path / "empty.txt"
    day_file.write_text("no entries here\n")
    assert count_entries(day_file) == 0


# --- resolve_entry_date ---

def test_resolve_entry_date():
    p = Path("2024-03-15.txt")
    assert resolve_entry_date(p, "%Y-%m-%d.txt") == date(2024, 3, 15)


def test_resolve_entry_date_no_match():
    p = Path("random.txt")
    assert resolve_entry_date(p, "%Y-%m-%d.txt") is None
