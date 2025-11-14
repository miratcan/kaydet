from __future__ import annotations

import pytest

from kaydet.parsers import Token, tokenize


def test_tokenize_simple_word():


    """Test that a single word is tokenized correctly."""


    tokens = tokenize("hello")


    assert tokens == [Token("WORD", "hello")]





def test_tokenize_tag():





    """Test that a single tag is tokenized correctly."""





    tokens = tokenize("#work")





    assert tokens == [Token("TAG", "work")]











def test_tokenize_metadata():











    """Test that a key:value pair is tokenized correctly."""











    tokens = tokenize("status:done")











    assert tokens == [Token("METADATA", ("status", "done"))]























def test_tokenize_complex_query():











    """Test that a query with multiple token types is tokenized correctly."""











    tokens = tokenize("search #work status:done")











    assert tokens == [











        Token("WORD", "search"),











        Token("TAG", "work"),











        Token("METADATA", ("status", "done")),











    ]


@pytest.mark.parametrize(
    "text, expected_token",
    [
        ("-#work", Token("EXCLUDE_TAG", "work")),
        ("-term", Token("EXCLUDE_WORD", "term")),
        ("-key:value", Token("EXCLUDE_METADATA", ("key", "value"))),
    ],
)
def test_tokenize_exclusion(text, expected_token):
    """Test that various exclusion patterns are tokenized correctly."""
    tokens = tokenize(text)
    assert tokens == [expected_token]


@pytest.mark.parametrize(
    "text, expected_token_type, expected_token_value",
    [
        ("https://example.com", "WORD", "https://example.com"),
        ("12:30", "WORD", "12:30"),
        ("key:value:with:colons", "METADATA", ("key", "value:with:colons")),
        ("word:", "WORD", "word:"),
        (":word", "WORD", ":word"),
    ],
)
def test_tokenize_edge_cases(text, expected_token_type, expected_token_value):
    """Test that edge cases with colons are handled correctly."""
    tokens = tokenize(text)
    assert len(tokens) == 1
    assert tokens[0].type == expected_token_type
    assert tokens[0].value == expected_token_value


@pytest.mark.parametrize(
    "text",
    [
        "Note:",
        "3:00",
        "3:1",
        "URL:",
        "http://example.com",
        "UPPER:case",
    ],
)
def test_tokenize_invalid_metadata_as_word(text):
    """Test that patterns resembling metadata but not matching the strict
    rules are treated as a single WORD token."""
    tokens = tokenize(text)
    assert tokens == [Token("WORD", text)]



















