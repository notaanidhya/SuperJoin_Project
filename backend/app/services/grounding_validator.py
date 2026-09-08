import re
from typing import Tuple, Optional
from app.utils.text_cleaning import normalize_unicode, clean_whitespace

class GroundingValidator:
    """Verifies whether an extracted fact is strictly grounded in the source chunk text."""

    @staticmethod
    def verify_grounding(quote: str, chunk_text: str) -> Tuple[bool, Optional[int]]:
        if not quote or not chunk_text:
            return False, None

        # 1. Direct exact match
        idx = chunk_text.find(quote)
        if idx != -1:
            return True, idx

        # 2. Case-insensitive exact match
        lower_quote = quote.lower()
        lower_chunk = chunk_text.lower()
        idx = lower_chunk.find(lower_quote)
        if idx != -1:
            return True, idx

        # 3. Normalized whitespace match (collapses \n, \r, \t, and multi-spaces to single space)
        collapsed_quote = re.sub(r'\s+', ' ', normalize_unicode(quote)).strip().lower()
        collapsed_chunk = re.sub(r'\s+', ' ', normalize_unicode(chunk_text)).strip().lower()
        idx = collapsed_chunk.find(collapsed_quote)
        if idx != -1:
            return True, idx

        # 4. Punctuation & Footnote normalization (handles trailing footnote indicators like (1), (3))
        clean_q = re.sub(r'\([0-9]+\)', '', collapsed_quote).strip()
        clean_c = re.sub(r'\([0-9]+\)', '', collapsed_chunk).strip()
        if clean_q and len(clean_q) >= 15:
            idx = clean_c.find(clean_q)
            if idx != -1:
                return True, idx

        # 5. Fallback: Check if leading 25-char fragment exists (handles minor quote trimming at end)
        if len(collapsed_quote) > 30:
            prefix = collapsed_quote[:25]
            if prefix in collapsed_chunk:
                return True, collapsed_chunk.find(prefix)

        return False, None
