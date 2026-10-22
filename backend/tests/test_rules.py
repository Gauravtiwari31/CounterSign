"""Table-driven tests: >= 5 cases per rule type, including negatives."""
import pytest

from app.lanes.rules.engine import RuleSpec, run_rules, validate_rule


def spec(type_, params, code="T1", channels=None):
    return RuleSpec(code=code, type=type_, params=params, severity="warning", channels=channels)


TERMINOLOGY = spec("terminology", {"preferred": "AloeCalm", "forbidden": ["Aloe-Calm", "Aloe Calm"]})
BANNED = spec("banned_phrase", {"phrases": ["guaranteed results", "miracle"]})
BANNED_ALT = spec("banned_phrase", {"phrases": ["anti-ageing"], "alternative": "age-care"})
REQUIRED = spec("required_phrase", {"text": "T&C apply", "trigger": r"\d+\s?%\s?off|\bfree\b"})
REQUIRED_END = spec("required_phrase", {"text": "#ad", "position": "end"})
PUNCT = spec("punctuation_limit", {"char": "!", "max_per_draft": 1, "max_run": 1})
LENGTH = spec("length_limit", {"limits": {"x": {"max_chars": 20}, "email": {"max_words": 3}}})
READ = spec("readability", {"max_sentence_words": 8})
CAPS = spec("all_caps", {"allow": ["SPF"], "min_length": 3})
HASHTAG = spec("hashtag", {"max_count": 2, "required": ["#VerdantSkin"]})
REGEX = spec("regex", {"pattern": r"\b(\d+)\s?per\s?cent\b", "flags": "i", "replacement": r"\1%"})
CURRENCY = spec("currency_format", {"symbol": "₹"})

CASES = [
    # (rule, channel, text, expected [(span_text, replacement)])
    (TERMINOLOGY, "instagram", "Try Aloe-Calm today", [("Aloe-Calm", "AloeCalm")]),
    (TERMINOLOGY, "instagram", "aloe calm and aloecalm", [("aloe calm", "AloeCalm"), ("aloecalm", "AloeCalm")]),
    (TERMINOLOGY, "instagram", "AloeCalm is here", []),
    (TERMINOLOGY, "instagram", "see verdant.in/aloe-calm-gel", []),  # inside a URL
    (TERMINOLOGY, "instagram", "#aloecalm #AloeCalm", []),  # hashtags exempt
    (TERMINOLOGY, "instagram", "Aloe Calm!", [("Aloe Calm", "AloeCalm")]),
    (BANNED, "x", "Guaranteed results in a week", [("Guaranteed results", None)]),
    (BANNED, "x", "a little miracle", [("miracle", None)]),
    (BANNED, "x", "miracles happen", []),  # word boundary
    (BANNED, "x", "results are not guaranteed", []),
    (BANNED_ALT, "x", "our anti-ageing cream", [("anti-ageing", "age-care")]),
    (BANNED_ALT, "x", "our anti ageing cream", [("anti ageing", "age-care")]),
    (REQUIRED, "x", "Now 20% off.", [("Now 20% off.", "Now 20% off. T&C apply")]),
    (REQUIRED, "x", "Now 20% off. T&C apply", []),
    (REQUIRED, "x", "A lovely gel.", []),  # no trigger
    (REQUIRED, "x", "Free gift inside.\nGrab it", [("Grab it", "Grab it T&C apply")]),
    (REQUIRED_END, "x", "Paid post #ad. More text here.", [("More text here.", "More text here. #ad")]),
    (PUNCT, "x", "Wow!!! Great!", [("!!!", "!"), ("!", ".")]),
    (PUNCT, "x", "Wow! Great.", []),
    (PUNCT, "x", 'Our partner "Yahoo!" says hi! Bye!', [("!", ".")]),  # quoted name exempt
    (PUNCT, "x", "Hi!! there", [("!!", "!")]),
    (PUNCT, "x", "No exclamation", []),
    (LENGTH, "x", "a" * 25, [("a" * 5, None)]),
    (LENGTH, "x", "short", []),
    (LENGTH, "email", "one two three four five", [("four five", None)]),
    (LENGTH, "instagram", "a" * 500, []),  # no limit for channel
    (LENGTH, "email", "one two three", []),
    (READ, "x", "This sentence is far too long for the limit we set here.", [("This sentence is far too long for the limit we set here.", None)]),
    (READ, "x", "Short one. Another short one.", []),
    (READ, "x", "Fine.\nThis one has quite a lot of words in it today ok.", [("This one has quite a lot of words in it today ok.", None)]),
    (READ, "x", "", []),
    (READ, "x", "One two three four five six seven eight.", []),
    (CAPS, "x", "This is AMAZING", [("AMAZING", "Amazing")]),
    (CAPS, "x", "Use SPF daily", []),
    (CAPS, "x", "OK go", []),  # below min length
    (CAPS, "x", "BUY NOW", [("BUY", "Buy"), ("NOW", "Now")]),
    (CAPS, "x", "visit #GLOWUP", []),
    (HASHTAG, "x", "#a #b #c #VerdantSkin", [("#c #VerdantSkin", None)]),
    (HASHTAG, "x", "Hello #VerdantSkin", []),
    (HASHTAG, "x", "Hello world", [("Hello world", "Hello world #VerdantSkin")]),
    (HASHTAG, "x", "Email me a@b.com #verdantskin", []),
    (HASHTAG, "x", "#one #verdantskin", []),
    (REGEX, "x", "Save 20 per cent", [("20 per cent", "20%")]),
    (REGEX, "x", "Save 15 percent now", [("15 percent", "15%")]),
    (REGEX, "x", "Save 20%", []),
    (REGEX, "x", "percentage points", []),
    (REGEX, "x", "5per cent", [("5per cent", "5%")]),
    (CURRENCY, "x", "Only Rs. 499", [("Rs. 499", "₹499")]),
    (CURRENCY, "x", "Only Rs 1,299", [("Rs 1,299", "₹1,299")]),
    (CURRENCY, "x", "INR 99", [("INR 99", "₹99")]),
    (CURRENCY, "x", "Only ₹499", []),
    (CURRENCY, "x", "Mrs 5 stars", []),
]


@pytest.mark.parametrize("rule,channel,text,expected", CASES)
def test_rule_cases(rule, channel, text, expected):
    hits = run_rules(text, channel, [rule])
    assert [(h.span_text, h.replacement) for h in hits] == expected
    for h in hits:
        assert text[h.start:h.end] == h.span_text


def test_channel_scoping():
    rule = spec("all_caps", {"min_length": 3}, channels=["instagram"])
    assert run_rules("LOUD", "x", [rule]) == []
    assert len(run_rules("LOUD", "instagram", [rule])) == 1


def test_validate_regex_rule_runs_its_test_strings():
    assert validate_rule("regex", {"pattern": "a+", "should_match": ["aaa"], "should_not_match": ["b"]}) == []
    errs = validate_rule("regex", {"pattern": "a+", "should_not_match": ["banana"]})
    assert errs and "wrongly matches" in errs[0]
    assert validate_rule("regex", {"pattern": "("})[0].startswith("pattern is not a valid regex")
    assert validate_rule("terminology", {}) == ["Missing parameter: preferred"]


def test_rules_lane_is_fast():
    import time

    rules = [TERMINOLOGY, BANNED, REQUIRED, PUNCT, LENGTH, READ, CAPS, HASHTAG, REGEX, CURRENCY]
    text = ("Say hello to Aloe-Calm!!! Our gel is a miracle and AMAZING, now 20% off at Rs. 499. " * 20)[:1800]
    run_rules(text, "instagram", rules)  # warm spaCy
    t = time.perf_counter()
    run_rules(text, "instagram", rules)
    assert time.perf_counter() - t < 0.05
