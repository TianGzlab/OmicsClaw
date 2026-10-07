"""Classify literature references without fetching or reading their contents."""
import re
from pathlib import Path


def detect_input_type(value):
    value = value.strip()
    if re.match(r'^10\.\d{4,}/\S+', value):
        return 'doi'
    if re.fullmatch(r'\d{7,8}', value):
        return 'pubmed'
    if value.startswith(('http://', 'https://')):
        return 'url'
    if len(value) < 4096:
        try:
            path = Path(value)
            if path.is_file() and path.suffix.lower() in ('.pdf', '.txt', '.md'):
                return 'file'
        except OSError:
            pass
    return 'text'
