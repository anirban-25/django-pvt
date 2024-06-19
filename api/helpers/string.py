import re
from difflib import SequenceMatcher


def similarity(a, b):
    """
    get similarity between two chars
    """
    return SequenceMatcher(None, a, b).ratio()


def ireplace(old, repl, text):
    return re.sub("(?i)" + re.escape(old), lambda m: repl, text)


def toAlphaNumeric(text, replacement="_"):
    if not text:
        return ""

    return re.sub(r"[^0-9a-zA-Z]+", replacement, text)


def add_space(content, length, head_or_tail="head", is_length_strict=True):
    _content = f"{content}"
    spaces = " " * (length - len(_content))

    if head_or_tail == "head":
        _content = spaces + _content
    else:
        _content = _content + spaces

    if is_length_strict:
        return _content[:length]
    else:
        return _content
    
def add_letter(content, length, head_or_tail="head", is_length_strict=True, letter="0"):
    _content = f"{content}"
    spaces = letter * (length - len(_content))

    if head_or_tail == "head":
        _content = spaces + _content
    else:
        _content = _content + spaces

    if is_length_strict:
        return _content[:length]
    else:
        return _content
