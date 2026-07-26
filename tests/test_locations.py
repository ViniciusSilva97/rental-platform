import pytest
from django.core.exceptions import ValidationError

from common.locations import (
    format_brazilian_postal_code,
    normalize_brazilian_postal_code,
    validate_brazilian_postal_code,
)


def test_normalize_and_format_brazilian_postal_code():
    assert normalize_brazilian_postal_code("01310-100") == "01310100"
    assert format_brazilian_postal_code("01310100") == "01310-100"


@pytest.mark.parametrize("value", ["0131010", "01310A00", "01310-1000"])
def test_reject_invalid_brazilian_postal_code(value):
    with pytest.raises(ValidationError):
        validate_brazilian_postal_code(value)
