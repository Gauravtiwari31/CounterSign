import logging

from app.pii import Masker

DRAFT = ("Call Riya on +91 98765 43210 or mail riya.sharma@example.com about AloeCalm. "
         "PAN ABCDE1234F, Aadhaar 1234 5678 9012.")


def test_masks_contacts_and_ids_but_not_products(caplog):
    m = Masker({"AloeCalm", "Verdant Skin"})
    masked = m.mask(DRAFT)
    logging.getLogger("countersign.llm").info("PROMPT %s", masked)
    for secret in ("98765 43210", "riya.sharma@example.com", "ABCDE1234F", "1234 5678 9012"):
        assert secret not in masked
        assert secret not in caplog.text
    assert "AloeCalm" in masked
    assert m.unmask(masked) == DRAFT


def test_same_value_same_placeholder():
    m = Masker()
    a = m.mask("mail a@b.com")
    b = m.mask("again a@b.com")
    assert a.split()[-1] == b.split()[-1] == "<EMAIL_1>"


def test_unmask_quote_from_llm():
    m = Masker()
    m.mask("Contact x@y.com today")
    assert m.unmask("Contact <EMAIL_1>") == "Contact x@y.com"
