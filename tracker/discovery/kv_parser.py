"""Minimal Valve KeyValues (VDF/ACF) parser.

Handles the subset of the KeyValues format used by Steam:
  - Quoted keys and values: "key" "value"
  - Nested blocks with { }
  - // line comments
  - No escape sequences (not needed for Steam manifests)
"""

from __future__ import annotations


class KVParserError(ValueError):
    """Raised when the input cannot be parsed."""


def _strip_comments(text: str) -> str:
    """Remove // line comments (not inside quotes)."""
    result: list[str] = []
    in_quotes = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_quotes = not in_quotes
            result.append(ch)
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/" and not in_quotes:
            # Skip to end of line
            while i < len(text) and text[i] != "\n":
                i += 1
            result.append("\n")
            continue
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _tokenise(text: str) -> list[str]:
    """Split text into tokens: quoted strings, '{', '}'."""
    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "{}":
            tokens.append(ch)
            i += 1
        elif ch == '"':
            # Find closing quote
            start = i
            i += 1
            while i < len(text) and text[i] != '"':
                i += 1
            if i >= len(text):
                raise KVParserError("Unterminated string literal")
            i += 1
            tokens.append(text[start:i])
        elif ch in " \t\n\r":
            i += 1
        else:
            raise KVParserError(
                f"Unexpected character {ch!r} at position {i} "
                f"(expected quoted string or '{{'/'}}')"
            )
    return tokens


def _parse_tokens(tokens: list[str]) -> dict:
    """Parse token list into nested dicts using a stack."""
    result: dict = {}
    stack: list[dict] = [result]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "{":
            # Expect previous token on stack top to accept the block
            stack.append({})
            i += 1
        elif token == "}":
            closed = stack.pop()
            if not stack:
                raise KVParserError("Unexpected closing brace '}'")
            # Attach closed dict to parent
            # It should already be attached via key assignment below
            i += 1
        else:
            # It's a quoted key
            if i + 1 >= len(tokens):
                raise KVParserError(f"Missing value for key {token}")
            key = token[1:-1]  # strip quotes
            next_tok = tokens[i + 1]
            if next_tok == "{":
                # Block value
                current = stack[-1]
                child: dict = {}
                current[key] = child
                stack.append(child)
                i += 2
            else:
                # String value
                value = next_tok[1:-1] if len(next_tok) >= 2 else ""
                stack[-1][key] = value
                i += 2
    if len(stack) != 1:
        raise KVParserError("Unclosed block (missing '}')")
    return result


def parse_kv(text: str) -> dict:
    """Parse Valve KeyValues text into a nested Python dict.

    Args:
        text: Raw VDF or ACF file content.

    Returns:
        Nested dict representation of the KeyValues data.

    Raises:
        KVParserError: If the input is malformed.
    """
    cleaned = _strip_comments(text)
    tokens = _tokenise(cleaned)
    return _parse_tokens(tokens)
