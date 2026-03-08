"""Basic tests for my_project package entry points."""

import pytest

from my_project import __version__, add, greet


def test_version() -> None:
    """Version should be a stable string literal for the package."""
    assert __version__ == "0.1.0"
    assert isinstance(__version__, str)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("World", "Hello, World!"),
        ("Alice", "Hello, Alice!"),
        ("", "Hello, !"),
    ],
)
def test_greet(name: str, expected: str) -> None:
    """Greet should include the provided name in output."""
    assert greet(name) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (1, 2, 3),
        (0, 0, 0),
        (-1, 1, 0),
        (-5, -3, -8),
        (-10, 5, -5),
    ],
)
def test_add(a: int, b: int, expected: int) -> None:
    """Add should return the expected integer sum."""
    assert add(a, b) == expected


@pytest.mark.parametrize(("a", "b"), [(3, 7), (-2, 9), (0, -4)])
def test_add_is_commutative(a: int, b: int) -> None:
    """Sanity check: order of operands should not change the sum."""
    assert add(a, b) == add(b, a)
