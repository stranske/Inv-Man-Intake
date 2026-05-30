"""Tests for sample my_project module."""

from my_project.main import add


def test_add_positive_numbers() -> None:
    assert add(2, 3) == 5


def test_add_with_negative_number() -> None:
    assert add(2, -5) == -3


def test_add_with_zero() -> None:
    assert add(0, 0) == 0
