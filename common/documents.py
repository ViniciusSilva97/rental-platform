import re

from django.core.exceptions import ValidationError

_DOCUMENT_FORMATTING = re.compile(r"[.\-/\s]")
_CPF_PATTERN = re.compile(r"^[0-9]{11}$")
_CNPJ_PATTERN = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")
_CPF_FIRST_DIGIT_WEIGHTS = tuple(range(10, 1, -1))
_CPF_SECOND_DIGIT_WEIGHTS = tuple(range(11, 1, -1))
_FIRST_DIGIT_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_SECOND_DIGIT_WEIGHTS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def normalize_cpf(value: str) -> str:
    """Return a CPF without formatting."""
    return _DOCUMENT_FORMATTING.sub("", value or "")


def normalize_cnpj(value: str) -> str:
    """Return a CNPJ without formatting and with uppercase letters."""
    return _DOCUMENT_FORMATTING.sub("", value or "").upper()


def _calculate_cpf_digit(characters: str, weights: tuple[int, ...]) -> str:
    pairs = zip(characters, weights, strict=False)
    total = sum(int(character) * weight for character, weight in pairs)
    remainder = total % 11
    return "0" if remainder < 2 else str(11 - remainder)


def calculate_cpf_check_digits(value: str) -> str:
    """Calculate the two check digits for the first nine CPF digits."""
    normalized = normalize_cpf(value)
    if len(normalized) != 9 or not normalized.isdigit():
        raise ValueError("A base do CPF deve conter nove números.")

    first_digit = _calculate_cpf_digit(normalized, _CPF_FIRST_DIGIT_WEIGHTS)
    second_digit = _calculate_cpf_digit(
        normalized + first_digit,
        _CPF_SECOND_DIGIT_WEIGHTS,
    )
    return first_digit + second_digit


def _calculate_check_digit(characters: str, weights: tuple[int, ...]) -> str:
    pairs = zip(characters, weights, strict=False)
    total = sum((ord(character) - 48) * weight for character, weight in pairs)
    remainder = total % 11
    return "0" if remainder in (0, 1) else str(11 - remainder)


def calculate_cnpj_check_digits(value: str) -> str:
    """Calculate the two check digits for the first 12 CNPJ characters."""
    normalized = normalize_cnpj(value)
    if len(normalized) != 12 or not re.fullmatch(r"[A-Z0-9]{12}", normalized):
        raise ValueError("A base do CNPJ deve conter 12 letras ou números.")

    first_digit = _calculate_check_digit(normalized, _FIRST_DIGIT_WEIGHTS)
    second_digit = _calculate_check_digit(
        normalized + first_digit,
        _SECOND_DIGIT_WEIGHTS,
    )
    return first_digit + second_digit


def validate_cnpj(value: str) -> None:
    """Validate numeric and alphanumeric CNPJs according to Receita Federal rules."""
    if not value:
        return

    normalized = normalize_cnpj(value)
    if not _CNPJ_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Informe um CNPJ com 14 posições: letras ou números nas 12 primeiras "
            "e números nas duas últimas.",
            code="invalid_cnpj_format",
        )

    if len(set(normalized)) == 1:
        raise ValidationError("Informe um CNPJ válido.", code="invalid_cnpj")

    if normalized[-2:] != calculate_cnpj_check_digits(normalized[:12]):
        raise ValidationError(
            "Os dígitos verificadores do CNPJ são inválidos.",
            code="invalid_cnpj",
        )


def validate_cpf(value: str) -> None:
    """Validate a Brazilian CPF."""
    if not value:
        return

    normalized = normalize_cpf(value)
    if not _CPF_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Informe um CPF com 11 números.",
            code="invalid_cpf_format",
        )

    if len(set(normalized)) == 1:
        raise ValidationError("Informe um CPF válido.", code="invalid_cpf")

    if normalized[-2:] != calculate_cpf_check_digits(normalized[:9]):
        raise ValidationError(
            "Os dígitos verificadores do CPF são inválidos.",
            code="invalid_cpf",
        )


def format_cpf(value: str | None) -> str:
    """Apply the CPF visual mask to a normalized value."""
    if not value:
        return ""

    normalized = normalize_cpf(value)
    if len(normalized) != 11:
        return normalized
    return (
        f"{normalized[:3]}.{normalized[3:6]}.{normalized[6:9]}-{normalized[9:]}"
    )


def format_cnpj(value: str | None) -> str:
    """Apply the official visual mask to a normalized CNPJ."""
    if not value:
        return ""

    normalized = normalize_cnpj(value)
    if len(normalized) != 14:
        return normalized
    return (
        f"{normalized[:2]}.{normalized[2:5]}.{normalized[5:8]}/"
        f"{normalized[8:12]}-{normalized[12:]}"
    )
