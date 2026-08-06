"""Tests for agent_credit_rating.py — CreditRating enum and transitions."""
from __future__ import annotations

import pytest

from maref.recursive.agent_credit_rating import CreditRating


class TestCreditRating:
    @pytest.mark.parametrize("rating,expected_value", [
        (CreditRating.AAA, 8),
        (CreditRating.AA, 7),
        (CreditRating.A, 6),
        (CreditRating.BBB, 5),
        (CreditRating.BB, 4),
        (CreditRating.B, 3),
        (CreditRating.C, 2),
        (CreditRating.D, 1),
    ])
    def test_numeric_value(self, rating, expected_value):
        assert rating.numeric_value == expected_value

    @pytest.mark.parametrize("rating,expected_floor", [
        (CreditRating.AAA, 0.90),
        (CreditRating.AA, 0.80),
        (CreditRating.A, 0.70),
        (CreditRating.BBB, 0.60),
        (CreditRating.BB, 0.50),
        (CreditRating.B, 0.40),
        (CreditRating.C, 0.25),
        (CreditRating.D, 0.0),
    ])
    def test_trust_floor(self, rating, expected_floor):
        assert rating.trust_floor == expected_floor

    @pytest.mark.parametrize("rating,expected", [
        (CreditRating.AAA, True),
        (CreditRating.AA, True),
        (CreditRating.A, True),
        (CreditRating.BBB, True),
        (CreditRating.BB, False),
        (CreditRating.B, False),
        (CreditRating.C, False),
        (CreditRating.D, False),
    ])
    def test_allowed_evolution(self, rating, expected):
        assert rating.allowed_evolution is expected

    @pytest.mark.parametrize("rating,expected", [
        (CreditRating.AAA, False),
        (CreditRating.AA, False),
        (CreditRating.A, False),
        (CreditRating.BBB, False),
        (CreditRating.BB, False),
        (CreditRating.B, True),
        (CreditRating.C, True),
        (CreditRating.D, True),
    ])
    def test_requires_human_review(self, rating, expected):
        assert rating.requires_human_review is expected

    @pytest.mark.parametrize("current,expected", [
        (CreditRating.D, CreditRating.C),
        (CreditRating.C, CreditRating.B),
        (CreditRating.B, CreditRating.BB),
        (CreditRating.BB, CreditRating.BBB),
        (CreditRating.BBB, CreditRating.A),
        (CreditRating.A, CreditRating.AA),
        (CreditRating.AA, CreditRating.AAA),
        (CreditRating.AAA, CreditRating.AAA),
    ])
    def test_next_up(self, current, expected):
        assert current.next_up() == expected

    @pytest.mark.parametrize("current,expected", [
        (CreditRating.AAA, CreditRating.AA),
        (CreditRating.AA, CreditRating.A),
        (CreditRating.A, CreditRating.BBB),
        (CreditRating.BBB, CreditRating.BB),
        (CreditRating.BB, CreditRating.B),
        (CreditRating.B, CreditRating.C),
        (CreditRating.C, CreditRating.D),
        (CreditRating.D, CreditRating.D),
    ])
    def test_next_down(self, current, expected):
        assert current.next_down() == expected
