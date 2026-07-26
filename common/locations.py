import re

from django.core.exceptions import ValidationError

_POSTAL_CODE_FORMATTING = re.compile(r"[-\s]")
_BRAZILIAN_POSTAL_CODE_PATTERN = re.compile(r"^[0-9]{8}$")


def normalize_brazilian_postal_code(value: str) -> str:
    """Return a Brazilian postal code without formatting."""
    return _POSTAL_CODE_FORMATTING.sub("", value or "")


def validate_brazilian_postal_code(value: str) -> None:
    """Validate a Brazilian postal code with eight digits."""
    normalized = normalize_brazilian_postal_code(value)
    if not _BRAZILIAN_POSTAL_CODE_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Informe um CEP com oito números.",
            code="invalid_postal_code",
        )


def format_brazilian_postal_code(value: str | None) -> str:
    """Apply the Brazilian postal-code visual mask."""
    if not value:
        return ""

    normalized = normalize_brazilian_postal_code(value)
    if len(normalized) != 8:
        return normalized
    return f"{normalized[:5]}-{normalized[5:]}"
