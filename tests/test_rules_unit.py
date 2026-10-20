"""Unit tests for the name-format and gibberish detectors.   python -m tests.test_rules_unit"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.integrity import gibberish_reason, name_issues  # noqa: E402

NAMES = {  # value -> expected set of (severity) messages' severities, or [] for OK
    "Dela Cruz, Juan, Santos": [],
    "Reyes, Maria Luisa, Capitanea": [],
    "O'Brien, Sean, De La Cruz": [],
    "Juan Santos": ["Major"],                       # no commas
    "Cruz, Juan": ["Minor"],                        # middle name missing
    "Cruz,Juan,Santos": ["Minor"],                  # no space after comma
    "DELA CRUZ, JUAN, SANTOS": ["Minor"],           # capitals
    "dela cruz, juan, santos": ["Minor"],           # lowercase
    "Cruz2, Juan, Santos": ["Major"],               # digit
    "Cruz, J, Santos": ["Major"],                   # single-letter first name
    "Cruz, , Santos": ["Major"],                    # empty part
    "": [],
}
for v, exp in NAMES.items():
    got = sorted({sev for sev, _ in name_issues(v)})
    assert got == sorted(set(exp)), (v, got, exp)

BAD = ["asdfgh", "test", "xxx", "qwerty123", "hahahahaha", "Mmmmmmmm", "sdfsdfsdf", "Bgtrkplmn", "aaaaaa", "lalala", "jkl;", "wala"]
GOOD = ["Dela Cruz, Juan, Santos", "Family cooperative", "Farmer", "Needs follow-up visit", "Strengths", "Mangsuprem", "Tboli"]
for v in BAD:
    assert gibberish_reason(v, "member_full_name"), f"should be flagged: {v}"
for v in GOOD:
    assert not gibberish_reason(v, "enumerator_remarks"), f"false positive: {v} -> {gibberish_reason(v, 'enumerator_remarks')}"
assert not gibberish_reason("none", "enumerator_remarks") and not gibberish_reason("N/A", "member_remarks")
assert gibberish_reason("none", "member_full_name")
print(f"name-format ({len(NAMES)}) and gibberish ({len(BAD)}+{len(GOOD)}) unit tests passed")
