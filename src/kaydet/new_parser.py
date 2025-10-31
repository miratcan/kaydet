from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass
class Token:
    type: str
    value: str | tuple[str, str]

def _parse_base_token(word: str) -> Token:
    """Parses a word into a single non-exclusion token."""
    # Explicitly check for URL schemes to prevent them from being parsed as metadata.
    if "://" in word:
        return Token("WORD", word)

    if word.startswith("#"):
        return Token("TAG", word[1:])

    # A key must start with a lowercase letter, followed by letters, numbers, _, or -.
    if re.match(r"^[a-z][a-z0-9_-]*:", word):
        parts = word.split(":", 1)
        # This check is slightly redundant due to the regex, but safe.
        if len(parts) == 2 and parts[0] and parts[1]:
            return Token("METADATA", (parts[0], parts[1]))

    return Token("WORD", word)





def tokenize(text: str) -> list[Token]:

    """Converts a search query string into a list of tokens."""

    tokens = []

    for word in text.split():

        if word.startswith("-") and len(word) > 1:

            base_token = _parse_base_token(word[1:])

            # Construct the exclusion token

            tokens.append(Token(f"EXCLUDE_{base_token.type}", base_token.value))

        else:

            tokens.append(_parse_base_token(word))

    return tokens