import re
import unicodedata

def normalize_unicode(text: str) -> str:
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', text)
    for char in ['\u2018', '\u2019', '\u201b', '\u2032']:
        text = text.replace(char, "'")
    for char in ['\u201c', '\u201d', '\u201f', '\u2033']:
        text = text.replace(char, '"')
    for char in ['\u2013', '\u2014', '\u2015']:
        text = text.replace(char, ' - ')
    for char in ['\u00a0', '\u1680', '\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005', '\u2006', '\u2007', '\u2008', '\u2009', '\u200a', '\u202f', '\u205f', '\u3000']:
        text = text.replace(char, ' ')
    return text


def fix_hyphenation(text: str) -> str:
    return re.sub(r"(\b[a-zA-Z]+)-\s*\n\s*([a-zA-Z]+\b)", r"\1\2", text)


def clean_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                cleaned.append("")
                prev_empty = True
        else:
            cleaned.append(line)
            prev_empty = False
    return "\n".join(cleaned).strip()


def clean_table_cell(cell) -> str:
    if cell is None:
        return ""
    cleaned = str(cell).replace("\n", " ").strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = cleaned.replace("|", "\\|")
    return cleaned


def clean_page_text(text: str) -> str:
    t = normalize_unicode(text)
    t = fix_hyphenation(t)
    t = clean_whitespace(t)
    return t
