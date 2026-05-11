"""
KAT grade conversion from numeric score.
"""


GRADE_TABLE = [
    (90, "A+"),
    (85, "A"),
    (80, "A-"),
    (75, "B+"),
    (70, "B"),
    (65, "B-"),
    (55, "C"),
    (0,  "D"),
]

GRADE_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C", "D"]


def score_to_grade(score: float) -> str:
    for threshold, grade in GRADE_TABLE:
        if score >= threshold:
            return grade
    return "D"


def grade_to_min_score(grade: str) -> float:
    """Return the minimum numeric score for a given grade string."""
    for threshold, g in GRADE_TABLE:
        if g == grade:
            return threshold
    return 0.0


def grade_passes_minimum(grade: str, min_grade: str) -> bool:
    """
    Returns True if `grade` is at least as good as `min_grade`.
    e.g. grade_passes_minimum("A", "B+") -> True
         grade_passes_minimum("B", "A-") -> False
    """
    if min_grade not in GRADE_ORDER:
        return True  # unknown min_grade — don't filter
    grade_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER)
    min_idx = GRADE_ORDER.index(min_grade)
    return grade_idx <= min_idx  # lower index = better grade


def format_grade_with_color(grade: str) -> str:
    """Return grade with ANSI color codes for terminal output."""
    colors = {
        "A+": "\033[92m",   # bright green
        "A":  "\033[92m",
        "A-": "\033[32m",   # green
        "B+": "\033[96m",   # cyan
        "B":  "\033[96m",
        "B-": "\033[93m",   # yellow
        "C":  "\033[33m",   # orange/yellow
        "D":  "\033[91m",   # red
    }
    reset = "\033[0m"
    color = colors.get(grade, "")
    return f"{color}{grade}{reset}"
