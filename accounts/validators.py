import re
from typing import Optional

from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

_SETUP_STRIP_RE = re.compile(r'[\s\-().]+')
_NP_MOBILE_RE = re.compile(r'^9\d{9}$')
_E164_RE = re.compile(r'^\+\d{8,15}$')


def strip_phone(value) -> str:
    """Remove spaces, dashes, parentheses and dots; keep digits and leading +."""
    return _SETUP_STRIP_RE.sub('', value or '')


def is_valid(value) -> bool:
    return normalize_phone(value) is not None


def normalize_phone(value) -> Optional[str]:
    """Return a normalized E.164-ish phone string, or None if unrecognized.

    Accepted inputs:
    - E.164 with leading plus (``+9779811000000``)
    - international ``00`` prefix (``009779811000000``)
    - bare 10-digit Nepali mobile number (``9811000000`` -> ``+9779811000000``)
    """
    cleaned = strip_phone(value)
    if not cleaned:
        return None
    if cleaned.startswith('+'):
        return cleaned if _E164_RE.fullmatch(cleaned) else None
    if cleaned.startswith('00'):
        candidate = '+' + cleaned[2:]
        return candidate if _E164_RE.fullmatch(candidate) else None
    if _NP_MOBILE_RE.fullmatch(cleaned):
        return '+977' + cleaned
    return None


class E164RegexValidator(RegexValidator):
    regex = _E164_RE
    message = _('Enter a valid phone number.')
    code = 'invalid'