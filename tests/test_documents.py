import pytest
from django.core.exceptions import ValidationError

from common.documents import (
    calculate_cnpj_check_digits,
    format_cnpj,
    normalize_cnpj,
    validate_cnpj,
)


@pytest.mark.parametrize(
    "value,normalized",
    [
        ("12.345.678/0001-95", "12345678000195"),
        ("12.abc.345/01de-35", "12ABC34501DE35"),
    ],
)
def test_normalize_cnpj(value, normalized):
    assert normalize_cnpj(value) == normalized


@pytest.mark.parametrize("value", ["12.345.678/0001-95", "12.ABC.345/01DE-35"])
def test_validate_numeric_and_alphanumeric_cnpj(value):
    validate_cnpj(value)


@pytest.mark.parametrize(
    "value",
    [
        "12.ABC.345/01DE-00",
        "12.ABC.345/01D!-35",
        "00000000000000",
        "123",
    ],
)
def test_reject_invalid_cnpj(value):
    with pytest.raises(ValidationError):
        validate_cnpj(value)


def test_calculate_and_format_alphanumeric_cnpj():
    assert calculate_cnpj_check_digits("12ABC34501DE") == "35"
    assert format_cnpj("12ABC34501DE35") == "12.ABC.345/01DE-35"
