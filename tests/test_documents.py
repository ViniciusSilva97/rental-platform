import pytest
from django.core.exceptions import ValidationError

from common.documents import (
    calculate_cnpj_check_digits,
    calculate_cpf_check_digits,
    format_cnpj,
    format_cpf,
    normalize_cnpj,
    normalize_cpf,
    validate_cnpj,
    validate_cpf,
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


def test_normalize_calculate_validate_and_format_cpf():
    assert normalize_cpf("529.982.247-25") == "52998224725"
    assert calculate_cpf_check_digits("529982247") == "25"
    validate_cpf("529.982.247-25")
    assert format_cpf("52998224725") == "529.982.247-25"


@pytest.mark.parametrize("value", ["529.982.247-00", "111.111.111-11", "123"])
def test_reject_invalid_cpf(value):
    with pytest.raises(ValidationError):
        validate_cpf(value)
