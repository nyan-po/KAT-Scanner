"""Tests for KAT grade conversion."""
import pytest
from src.grading import score_to_grade, grade_to_min_score, grade_passes_minimum


class TestScoreToGrade:
    def test_90_plus_is_a_plus(self):
        assert score_to_grade(95) == "A+"
        assert score_to_grade(90) == "A+"
        assert score_to_grade(100) == "A+"

    def test_85_to_89_is_a(self):
        assert score_to_grade(85) == "A"
        assert score_to_grade(89) == "A"

    def test_80_to_84_is_a_minus(self):
        assert score_to_grade(80) == "A-"
        assert score_to_grade(84) == "A-"

    def test_75_to_79_is_b_plus(self):
        assert score_to_grade(75) == "B+"
        assert score_to_grade(79) == "B+"

    def test_70_to_74_is_b(self):
        assert score_to_grade(70) == "B"
        assert score_to_grade(74) == "B"

    def test_65_to_69_is_b_minus(self):
        assert score_to_grade(65) == "B-"
        assert score_to_grade(69) == "B-"

    def test_55_to_64_is_c(self):
        assert score_to_grade(55) == "C"
        assert score_to_grade(64) == "C"

    def test_below_55_is_d(self):
        assert score_to_grade(54) == "D"
        assert score_to_grade(0) == "D"

    def test_boundary_exactly_90(self):
        assert score_to_grade(90) == "A+"

    def test_boundary_exactly_85(self):
        assert score_to_grade(85) == "A"

    def test_boundary_exactly_55(self):
        assert score_to_grade(55) == "C"


class TestGradeToMinScore:
    def test_a_plus_threshold(self):
        assert grade_to_min_score("A+") == 90

    def test_b_threshold(self):
        assert grade_to_min_score("B") == 70

    def test_d_threshold(self):
        assert grade_to_min_score("D") == 0

    def test_unknown_grade(self):
        assert grade_to_min_score("Z") == 0.0


class TestGradePassesMinimum:
    def test_a_plus_passes_b(self):
        assert grade_passes_minimum("A+", "B") is True

    def test_b_fails_a_minus(self):
        assert grade_passes_minimum("B", "A-") is False

    def test_same_grade_passes(self):
        assert grade_passes_minimum("B+", "B+") is True

    def test_d_fails_b(self):
        assert grade_passes_minimum("D", "B") is False

    def test_a_minus_fails_a(self):
        assert grade_passes_minimum("A-", "A") is False

    def test_a_plus_passes_a_minus(self):
        assert grade_passes_minimum("A+", "A-") is True

    def test_unknown_min_grade_always_passes(self):
        assert grade_passes_minimum("D", "Z") is True
