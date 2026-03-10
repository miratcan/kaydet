from kaydet.parsers import extract_tags_from_text, partition_entry_tokens


def test_extract_tags_ignores_escaped_hash():
    text = r"literal \#notatag and #real"
    tags = extract_tags_from_text(text)
    assert tags == ("real",)


def test_partition_entry_tokens_keeps_literal_hash():
    tokens = [r"Note about \#notatag #work"]
    message_tokens, metadata, tags = partition_entry_tokens(tokens)
    assert message_tokens == ["Note about #notatag"]
    assert tags == ["work"]
    assert metadata == {}
