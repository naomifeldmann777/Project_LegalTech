"""test_placeholders.py - automatic tests for placeholders.py.

What this file is for:
    It proves that the gaps of the clauses are filled correctly:
    - CHF amounts, percentages and dates are formatted as agreed (decision D35)
    - milestone amounts follow the rounding rule: half-up to cents, the last
      instalment takes the balance, and the amounts always add up exactly to the
      price (handoff App. B, decision D23)
    - the derived texts use the wording from clauses.yaml (handoff App. D,
      law packet page 7)
    - fill_text() replaces every {name} that has a value and leaves the others

How it fits into the project:
    AI_PROMPT step 9 ("Tests incl. rounding"). Run from the project root:
        python -m pytest tests/test_placeholders.py -v

Which documents it implements:
    Handoff App. B (milestone rounding), App. D (deterministic text assembly),
    scenarios P2 and P8 (AI_PROMPT section 9), decisions D23, D35, D36.
"""

from datetime import date  # to build test dates
from decimal import Decimal  # exact money values for the tests (never float)

import pytest  # the test framework: fixtures, parametrize and pytest.raises

from data_loader import load_knowledge  # the real knowledge base, so tests use the real wording
from placeholders import (  # the functions under test
    build_derived,  # builds one derived text
    build_values,  # all values of one clause
    fill_text,  # puts values into a text
    format_chf,  # CHF format
    format_date,  # date format
    format_percent,  # percentage format
    format_value,  # format by field type
    milestone_amounts,  # rounding rule for instalments
)  # end of the imports


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")  # load the YAML files once for all tests in this file
def knowledge():
    """The real knowledge base from data/ (wording exactly as in clauses.yaml)."""
    return load_knowledge()  # read and check the four YAML files


def p2_answers(price_type="fixed"):
    """Answers like scenario P2: CHF 100,000.00, VAT included, milestones 20 / 40 / 40,
    the first milestone an advance with trigger "Contract signed".

    price_type can be changed to "estimate" to test the estimate wording.
    """
    return {  # the answers dictionary, as the app will build it
        "price_type": price_type,  # fixed or estimate
        "contract_price": Decimal("100000.00"),  # the price
        "vat_treatment": "included",  # VAT included
        "payment_type": "milestones",  # milestone payments
        "milestones": [  # the three rows of the milestone table
            {"name": "Deposit", "trigger": "Contract signed", "percent": Decimal("20"),
             "invoice_due_days": 10, "advance": True},  # row 1: advance payment
            {"name": "Shell construction", "trigger": "Roof is closed", "percent": Decimal("40"),
             "invoice_due_days": 30, "advance": False},  # row 2
            {"name": "Handover", "trigger": "Works delivered", "percent": Decimal("40"),
             "invoice_due_days": 30, "advance": False},  # row 3
        ],  # end of the rows
    }  # end of the answers


# ---------------------------------------------------------------------------
# 1. Formatting (decision D35)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(  # run the same test with several inputs
    "amount, expected",  # names of the two values in each case below
    [  # the cases
        (Decimal("100000"), "100,000.00"),  # thousands separator and 2 decimals
        (Decimal("1234567.5"), "1,234,567.50"),  # millions
        (Decimal("0.005"), "0.01"),  # half a cent is rounded up (half-up)
        (Decimal("10.004"), "10.00"),  # less than half a cent is rounded down
    ],  # end of the cases
)  # end of parametrize
def test_format_chf(amount, expected):
    """CHF amounts get thousands separators and exactly 2 decimals."""
    assert format_chf(amount) == expected  # compare with the expected text


@pytest.mark.parametrize(  # several inputs for the same test
    "value, expected",  # names of the two values
    [  # the cases
        (Decimal("20"), "20"),  # whole number
        (Decimal("20.00"), "20"),  # trailing zeros are dropped
        (Decimal("12.50"), "12.5"),  # one trailing zero is dropped
        (Decimal("33.33"), "33.33"),  # two decimals stay
    ],  # end of the cases
)  # end of parametrize
def test_format_percent(value, expected):
    """Percentages are shown without unnecessary zeros."""
    assert format_percent(value) == expected  # compare with the expected text


def test_format_date():
    """Dates are written as day, month name and year."""
    assert format_date(date(2027, 12, 31)) == "31 December 2027"  # end of a year
    assert format_date(date(2026, 1, 1)) == "1 January 2026"  # no leading zero for the day


def test_format_value_uses_the_field_type(knowledge):
    """format_value picks the right format from the field's type in parameters.yaml."""
    fields = knowledge["fields"]  # the field definitions
    assert format_value(fields["contract_price"], Decimal("5000")) == "5,000.00"  # decimal_chf
    assert format_value(fields["contract_date"], date(2026, 11, 1)) == "1 November 2026"  # date
    assert format_value(fields["estimate_basis"], "Hourly rate") == "Hourly rate"  # text stays text
    with pytest.raises(ValueError):  # a list cannot go into a sentence directly
        format_value(fields["milestones"], [])  # milestones is a list field


# ---------------------------------------------------------------------------
# 2. Milestone amounts and the rounding rule (handoff App. B, decision D23)
# ---------------------------------------------------------------------------

def test_amounts_for_scenario_p2():
    """P2: CHF 100,000.00 split 20 / 40 / 40."""
    amounts = milestone_amounts(Decimal("100000.00"), [Decimal("20"), Decimal("40"), Decimal("40")])  # split
    assert amounts == [Decimal("20000.00"), Decimal("40000.00"), Decimal("40000.00")]  # expected instalments


def test_amounts_for_scenario_p8_last_takes_the_balance():
    """P8: CHF 99,999.99 split 50 / 50; 49,999.995 is rounded up, the last takes the balance."""
    amounts = milestone_amounts(Decimal("99999.99"), [Decimal("50"), Decimal("50")])  # split
    assert amounts == [Decimal("50000.00"), Decimal("49999.99")]  # first rounded up, last = balance


def test_amounts_round_half_up_not_half_even():
    """Half a cent is always rounded up (D23); "banker's rounding" would give 50,000.00 here."""
    amounts = milestone_amounts(Decimal("100000.01"), [Decimal("50"), Decimal("50")])  # 50,000.005 each
    assert amounts == [Decimal("50000.01"), Decimal("50000.00")]  # half-up, then the balance


@pytest.mark.parametrize(  # several prices and splits
    "price, percents",  # names of the two values
    [  # the cases
        ("99999.99", ["33.33", "33.33", "33.34"]),  # thirds of an odd price
        ("100000.01", ["50", "50"]),  # half cents
        ("12345.67", ["10", "20", "30", "40"]),  # four rows
        ("1000.00", ["12.5", "12.5", "75"]),  # decimals in the percentages
        ("777.77", ["100"]),  # one single milestone
    ],  # end of the cases
)  # end of parametrize
def test_amounts_always_add_up_exactly_to_the_price(price, percents):
    """Whatever the split, the instalments add up exactly to the price and have at most 2 decimals."""
    price = Decimal(price)  # text to Decimal (exact)
    amounts = milestone_amounts(price, [Decimal(p) for p in percents])  # split
    assert sum(amounts) == price  # no cent lost or added
    assert all(amount == amount.quantize(Decimal("0.01")) for amount in amounts)  # whole cents only


def test_amounts_for_no_milestones():
    """No percentages give no amounts (R_PAY reports the missing rows)."""
    assert milestone_amounts(Decimal("1000"), []) == []  # empty in, empty out


# ---------------------------------------------------------------------------
# 3. Derived texts (handoff App. D, law packet page 7)
# ---------------------------------------------------------------------------

def test_vat_treatment_text(knowledge):
    """vat_treatment_text uses the App. D sentence for each answer."""
    placeholder = knowledge["derived_placeholders"]["vat_treatment_text"]  # its definition
    assert build_derived(placeholder, {"vat_treatment": "included"}) == "This amount includes applicable VAT."  # included
    assert build_derived(placeholder, {"vat_treatment": "not_charged"}) == "No VAT is charged on this amount."  # no VAT
    assert build_derived(placeholder, {}) is None  # unanswered: no text, the gap stays open


def test_milestone_reconciliation_text(knowledge):
    """milestone_reconciliation_text depends on the price type (App. D)."""
    placeholder = knowledge["derived_placeholders"]["milestone_reconciliation_text"]  # its definition
    assert build_derived(placeholder, {"price_type": "fixed"}) == "The schedule allocates the fixed price."  # fixed
    assert build_derived(placeholder, {"price_type": "estimate"}).startswith("These are advances against the final price.")  # estimate


def test_every_derived_placeholder_in_the_yaml_can_be_built(knowledge):
    """Every derived placeholder declared in clauses.yaml has a builder (decision D10)."""
    for placeholder in knowledge["derived_placeholders"].values():  # each declared placeholder
        text = build_derived(placeholder, p2_answers())  # must not raise "no builder"
        assert isinstance(text, str) and text  # and must give a non-empty text


def test_unknown_derived_placeholder_needs_a_builder():
    """A derived placeholder without text_by_answer and without a special builder is reported."""
    with pytest.raises(ValueError, match="no builder"):  # the error message mentions the missing builder
        build_derived({"id": "new_placeholder", "chosen_by": "price_type"}, p2_answers())  # unknown kind


# ---------------------------------------------------------------------------
# 4. The milestone schedule (law packet page 7, decision D36)
# ---------------------------------------------------------------------------

def test_schedule_for_scenario_p2_fixed(knowledge):
    """P2 with a fixed price: one numbered line per milestone, with amounts and advance labels."""
    schedule = build_derived(knowledge["derived_placeholders"]["milestones_schedule"], p2_answers())  # build it
    lines = schedule.strip().split("\n")  # one line per milestone
    assert len(lines) == 3  # three milestones
    assert lines[0] == (  # the full first line, word for word
        "1. Deposit | Trigger: Contract signed | Share of fixed price: 20% | Instalment: CHF 20,000.00 | "
        "Invoice period: 10 calendar days after receipt | "
        "Pre-performance advance: payable before the corresponding work is performed."
    )  # end of the expected line
    assert lines[1].startswith("2. Shell construction | Trigger: Roof is closed | Share of fixed price: 40% | Instalment: CHF 40,000.00")  # row 2
    assert lines[1].endswith("No pre-performance advance: this instalment follows the stated performance trigger.")  # no advance
    assert schedule.startswith("\n") and schedule.endswith("\n")  # the schedule stands on its own lines


def test_schedule_for_an_estimate_uses_the_estimate_wording(knowledge):
    """With an estimate, each line uses the estimate wording of law packet page 7."""
    schedule = build_derived(knowledge["derived_placeholders"]["milestones_schedule"], p2_answers("estimate"))  # build it
    assert "Share of estimated schedule base: 20% | Provisional payment on account: CHF 20,000.00" in schedule  # row 1
    assert "Share of fixed price" not in schedule  # no fixed-price wording


def test_schedule_without_milestones_stays_open(knowledge):
    """Without milestone rows, no schedule is built, so the gap stays open."""
    answers = p2_answers()  # start from P2
    answers["milestones"] = []  # but with no rows
    assert build_derived(knowledge["derived_placeholders"]["milestones_schedule"], answers) is None  # nothing built


# ---------------------------------------------------------------------------
# 5. Values of a whole clause, and filling a text
# ---------------------------------------------------------------------------

def test_build_values_for_price_fixed(knowledge):
    """PRICE_FIXED gets the formatted price and the VAT sentence."""
    values = build_values(knowledge["clauses"]["PRICE_FIXED"], p2_answers(), knowledge)  # values of the clause
    assert values == {  # exactly these two gaps
        "contract_price": "100,000.00",  # formatted price
        "vat_treatment_text": "This amount includes applicable VAT.",  # derived sentence
    }  # end of the expected values


def test_build_values_leaves_out_missing_answers(knowledge):
    """A missing answer gives no value, so the gap can be reported by the engine."""
    answers = p2_answers()  # start from P2
    del answers["contract_price"]  # the price is not answered
    values = build_values(knowledge["clauses"]["PRICE_FIXED"], answers, knowledge)  # values of the clause
    assert "contract_price" not in values  # no value for the missing answer
    assert "vat_treatment_text" in values  # the other gap is still filled


def test_build_values_for_a_clause_without_gaps(knowledge):
    """PAYMENT_ON_COMPLETION has no placeholders (App. D "Inputs: None")."""
    assert build_values(knowledge["clauses"]["PAYMENT_ON_COMPLETION"], p2_answers(), knowledge) == {}  # nothing to fill


def test_fill_text_replaces_known_names_and_keeps_unknown_ones():
    """Names with a value are replaced; names without a value stay as {name}."""
    text = "CHF {contract_price}. {vat_treatment_text}"  # a short text with two gaps
    assert fill_text(text, {"contract_price": "500.00"}) == "CHF 500.00. {vat_treatment_text}"  # only the known one


def test_fill_text_does_not_touch_braces_inside_answers():
    """Braces typed by the user are copied as they are and not treated as new gaps."""
    assert fill_text("Basis: {estimate_basis}.", {"estimate_basis": "rate {see annex}"}) == "Basis: rate {see annex}."  # unchanged


def test_fill_text_removes_spaces_around_line_breaks():
    """A schedule on its own lines does not leave spaces at the start or end of lines."""
    assert fill_text("elapsed. {schedule} The", {"schedule": "\n1. A\n2. B\n"}) == "elapsed.\n1. A\n2. B\nThe"  # tidy


def test_payment_milestone_clause_for_scenario_p2(knowledge):
    """The whole PAYMENT_MILESTONE clause for P2: all gaps filled, wording from App. D."""
    clause = knowledge["clauses"]["PAYMENT_MILESTONE"]  # the clause
    filled = fill_text(clause["text"], build_values(clause, p2_answers(), knowledge))  # fill all gaps
    assert "{" not in filled  # no gap is left (P2 has no braces in its answers)
    assert filled.startswith("Payments follow the milestone schedule below.")  # App. D wording kept
    assert "3. Handover | Trigger: Works delivered" in filled  # the schedule is inside
    assert filled.endswith("The schedule allocates the fixed price. Statutory payment defences remain reserved.")  # end
