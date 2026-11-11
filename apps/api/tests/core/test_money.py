from decimal import Decimal

import pytest

from marginos.core.money import D, q2, validate_currency


def test_q2_rounds_half_up():
    assert q2(D("1.005")) == Decimal("1.01")


def test_q2_keeps_two_places():
    assert str(q2(D("2"))) == "2.00"


def test_d_accepts_string_and_int():
    assert D("29.99") == Decimal("29.99")
    assert D(3) == Decimal("3")


def test_d_from_float_goes_through_repr():
    assert D(0.1) == Decimal("0.1")


def test_validate_currency_accepts_iso_code():
    assert validate_currency("USD") == "USD"


def test_validate_currency_rejects_lowercase():
    with pytest.raises(ValueError):
        validate_currency("usd")


def test_validate_currency_rejects_wrong_length():
    with pytest.raises(ValueError):
        validate_currency("US")
