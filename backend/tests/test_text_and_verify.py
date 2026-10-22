import uuid

from app.lanes.claims.verify import verify
from app.lanes.fixes.recheck import number_guard
from app.lanes.text import locate, normalise, split_sentences
from app.lanes.types import Claim, FactRow
from app.schemas.llm import Verdict

TEXT = "Say hello to AloeCalm! It’s clinically proven — clear skin in 7 days.\nShop now."


def test_locate_exact_and_hint():
    s, e = locate("clinically proven", TEXT)
    assert TEXT[s:e] == "clinically proven"


def test_locate_curly_quotes_dashes_whitespace():
    s, e = locate("It's clinically proven - clear skin in 7 days", TEXT)
    assert TEXT[s:e] == "It’s clinically proven — clear skin in 7 days"


def test_locate_case_insensitive():
    s, e = locate("SAY HELLO", TEXT)
    assert TEXT[s:e] == "Say hello"


def test_locate_fuzzy_inside_hint_only():
    sents = split_sentences(TEXT)
    hint = (sents[1].start, sents[1].end)
    span = locate("clinicaly proven - clear skin in 7 days", TEXT, hint)
    assert span is not None and "clinically proven" in TEXT[span[0]:span[1]]


def test_locate_rejects_near_misses():
    assert locate("clinically tested", TEXT) is None
    assert locate("clear skin in 3 days", TEXT) is None
    assert locate("", TEXT) is None


def test_split_sentences_offsets():
    for s in split_sentences(TEXT):
        assert TEXT[s.start:s.end] == s.text
    assert [s.text for s in split_sentences(TEXT)][-1] == "Shop now."


def _fact(code, statement):
    return FactRow(uuid.uuid4(), code, statement, "doc", "", "Regulatory", None, None, None, [], [], [])


CLAIM = Claim(0, 0, 10, "clear acne in 7 days", "health_benefit", "Clears acne in 7 days",
              candidates=[_fact("F-19", "In a four-week study, 68% saw fewer visible blemishes.")])


def test_verify_accepts_exact_substring_with_unicode_noise():
    v = Verdict(claim_index=0, verdict="contradicts", fact_code="F-19", evidence_quote="68%  saw fewer visible blemishes")
    assert verify(CLAIM, v).verified


def test_verify_downgrades_unknown_fact_code():
    v = Verdict(claim_index=0, verdict="supports", fact_code="F-99", evidence_quote="68% saw fewer visible blemishes")
    c = verify(CLAIM, v)
    assert c.verdict == "insufficient" and c.downgraded


def test_verify_downgrades_paraphrased_quote():
    v = Verdict(claim_index=0, verdict="contradicts", fact_code="F-19", evidence_quote="68% had clearer skin")
    c = verify(CLAIM, v)
    assert c.verdict == "insufficient" and c.note == "Model cited evidence that could not be verified"


def test_verify_rejects_trivial_quote():
    v = Verdict(claim_index=0, verdict="supports", fact_code="F-19", evidence_quote="68%")
    assert verify(CLAIM, v).downgraded


def test_number_guard():
    assert number_guard("In a four-week study, 68% saw fewer blemishes", "clear acne in 7 days",
                        ["In a four-week study, 68% saw fewer visible blemishes."])
    assert not number_guard("90% saw clear skin", "clear skin", [])
    assert number_guard("now ₹1,299", "Rs 1299", [])


def test_normalise():
    assert normalise("  “Hi” —  There ") == '"hi" - there'
