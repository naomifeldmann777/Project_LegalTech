"""test_engine.py - automatic tests for engine.py and checks.py.

What this file is for:
    It tests the rule engine piece by piece, with at least one test per rule
    (AI_PROMPT step 11): R_SCOPE, R_REQUIRED, R_PRICE, R_PAY, R_TERM, W_PRICE,
    W_CONSUMER, W_CURE, the SEL_ rules and R_CROSS. It also tests the condition operators, step 0
    (inactive answers are ignored), the special checks of checks.py, and the review
    records. Every test starts from one complete, valid project (like scenario P1)
    and changes only what the test is about.

How it fits into the project:
    The scenario tests (steps 12 and 13) check whole projects against the legal
    expectations; these tests check each part of the engine on its own. Run:
        python -m pytest tests/test_engine.py -v

Which documents it implements:
    Handoff App. B (missing vs. no, inactive inputs, milestone records), App. C
    (rules, review record), diagrams PDF ch. 2 (steps), decisions D6, D16-D20,
    D22, D24-D28, D42.
"""

import copy  # deepcopy: tests that change the knowledge base work on a copy
from datetime import date  # dates for the answers
from decimal import Decimal  # exact money and percentages (never float)

import pytest  # the test framework

from checks import is_empty  # the definition of "not answered"
from data_loader import load_knowledge  # the real knowledge base
from engine import condition_is_true, evaluate, is_active  # the functions under test


# ---------------------------------------------------------------------------
# Shared test data and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")  # load the YAML files once for all tests in this file
def knowledge():
    """The real knowledge base from data/."""
    return load_knowledge()  # read and check the four YAML files


def valid_answers():
    """A complete, valid project like scenario P1: fixed CHF 100,000.00, VAT included, payment on delivery."""
    return {  # every active field answered
        "contract_date": date(2026, 11, 1),  # after 1 January 2026
        "work_category": "immovable_residential_building",  # the supported category
        "scope_confirmed": True,  # scope confirmed
        "client_name": "Anna Muster",  # fictional client
        "client_address": "Seestrasse 1\n8000 Zürich",  # fictional address
        "contractor_name": "Bau AG",  # fictional contractor
        "contractor_address": "Werkweg 5\n3000 Bern",  # fictional address
        "site_address": "Seestrasse 1\n8000 Zürich",  # the site
        "work_description": "Renovation of the bathroom",  # the Works
        "exclusions_and_client_supplies": None,  # optional, left empty
        "annex_register": [],  # optional, no annexes
        "price_type": "fixed",  # fixed price
        "contract_price": Decimal("100000.00"),  # CHF 100,000.00
        "vat_treatment": "included",  # VAT included
        "payment_type": "on_completion",  # payment on delivery
        "delay_penalty": False,  # no delay penalty (and no binding date)
        "defect_notice_contact": "Bau AG, Werkweg 5, 3000 Bern",  # where defect notices go
        "liability_limit": False,  # statutory liability
        "termination_reasons": False,  # no extra grounds: statutory baseline
        "contractor_signatory_name": "Max Bau",  # who signs
        "contractor_signatory_capacity": "Managing director",  # in which capacity
    }  # end of the answers


def row(percent, name="Stage", trigger="Stage completed", days=30, advance=False):
    """One milestone row; percent is given as text and turned into a Decimal."""
    return {"name": name, "trigger": trigger, "percent": Decimal(percent),  # name, trigger, share
            "invoice_due_days": days, "advance": advance}  # days to pay, advance yes/no


def run(knowledge, **changes):
    """Evaluate the valid project with some answers changed, e.g. run(knowledge, contract_price=Decimal("0"))."""
    return evaluate({**valid_answers(), **changes}, knowledge)  # the valid answers, overwritten by the changes


def rule_ids(entries):
    """The rule IDs of a list of errors or warnings, e.g. ["R_PRICE", "R_PAY"]."""
    return [entry["rule_id"] for entry in entries]  # one ID per entry


def places(entries, rule_id):
    """The fields (or slots) where one rule fired, e.g. places(errors, "R_REQUIRED") -> ["client_name"]."""
    return [entry["field"] for entry in entries if entry["rule_id"] == rule_id]  # only that rule


def clause_ids(result):
    """The IDs of the selected clauses, in contract order."""
    return [record["clause_id"] for record in result["selected_clauses"]]  # one ID per record


# ---------------------------------------------------------------------------
# 1. Conditions (decision D6) and "not answered" (handoff App. B)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(  # one condition per case, with the expected result
    "condition, answers, expected",  # names of the three values
    [  # the cases
        ({"field": "a", "op": "equals", "value": "x"}, {"a": "x"}, True),  # same value
        ({"field": "a", "op": "equals", "value": "x"}, {}, False),  # missing answer is not equal
        ({"field": "a", "op": "not_equals", "value": True}, {"a": False}, True),  # different value
        ({"field": "a", "op": "not_equals", "value": True}, {}, True),  # missing answer counts as different
        ({"field": "a", "op": "less_than", "value": 5}, {"a": 4}, True),  # 4 < 5
        ({"field": "a", "op": "less_than", "value": 5}, {}, False),  # missing answer: order comparison is false
        ({"field": "a", "op": "at_most", "value": 0}, {"a": 0}, True),  # 0 <= 0
        ({"field": "a", "op": "greater_than", "value": 0}, {"a": 1}, True),  # 1 > 0
        ({"field": "a", "op": "at_least", "value": 1}, {"a": 0}, False),  # 0 >= 1 is false
        ({"field": "a", "op": "one_of", "value": ["x", "y"]}, {"a": "y"}, True),  # y is in the list
        ({"field": "a", "op": "is_empty"}, {"a": "  "}, True),  # only spaces = empty
        ({"field": "a", "op": "is_filled"}, {"a": False}, True),  # False is an answer ("no")
        ({"always": True}, {}, True),  # always true
        ({"all": [{"always": True}, {"field": "a", "op": "is_empty"}]}, {"a": 1}, False),  # AND: one part false
        ({"any": [{"field": "a", "op": "is_empty"}, {"always": True}]}, {"a": 1}, True),  # OR: one part true
        ({"not": {"field": "a", "op": "is_empty"}}, {"a": 1}, True),  # NOT empty
    ],  # end of the cases
)  # end of parametrize
def test_condition_operators(condition, answers, expected):
    """Every operator of the structured YAML conditions works as described in rules.yaml."""
    assert condition_is_true(condition, answers) is expected  # compare with the expected result


def test_is_empty_treats_false_as_an_answer():
    """None, blank text and empty lists are "not answered"; False and 0 are answers (handoff App. B)."""
    assert is_empty(None) and is_empty("") and is_empty("   ") and is_empty([])  # not answered
    assert not is_empty(False) and not is_empty(0) and not is_empty(Decimal("0"))  # answered


def test_is_active_follows_active_when(knowledge):
    """estimate_basis is only active for estimates, milestones only for milestone payments."""
    assert is_active("estimate_basis", {"price_type": "estimate"}, knowledge)  # estimate: shown
    assert not is_active("estimate_basis", {"price_type": "fixed"}, knowledge)  # fixed: hidden
    assert is_active("milestones", {"payment_type": "milestones"}, knowledge)  # milestones: shown
    assert not is_active("milestones", {"payment_type": "on_completion"}, knowledge)  # on delivery: hidden
    assert is_active("contract_price", {}, knowledge)  # no active_when: always shown


# ---------------------------------------------------------------------------
# 2. Step 0: inactive and unknown answers (handoff App. B, E8, decision D26)
# ---------------------------------------------------------------------------

def test_inactive_milestones_are_ignored(knowledge):
    """Old milestones 30/30/30 are ignored when paying on delivery (scenario P9)."""
    result = run(knowledge, milestones=[row("30"), row("30"), row("30")])  # payment_type stays on_completion
    assert "R_PAY" not in rule_ids(result["errors"])  # the invalid old rows do not cause an error
    assert result["ignored_fields"] == ["milestones"]  # but they are listed as ignored
    assert result["can_generate"]  # the contract can be generated


def test_unknown_answers_are_ignored(knowledge):
    """Answers for fields that are not in parameters.yaml (e.g. client_owns_site, left out on purpose) are ignored."""
    result = run(knowledge, client_owns_site=True, insurance_cover="1000000")  # fields that do not exist in parameters.yaml
    assert result["ignored_fields"] == ["client_owns_site", "insurance_cover"]  # listed as ignored
    assert result["can_generate"]  # no effect on the result


def test_empty_inactive_answers_are_not_listed_as_ignored(knowledge):
    """An inactive field without a value is simply left out, not reported as ignored."""
    result = run(knowledge, estimate_basis="")  # price is fixed, basis empty
    assert result["ignored_fields"] == []  # nothing worth mentioning


def test_floats_are_refused(knowledge):
    """Money as float is refused with a clear message (decision D25)."""
    with pytest.raises(TypeError, match="contract_price"):  # the message names the field
        run(knowledge, contract_price=100000.0)  # float instead of Decimal


def test_floats_inside_milestones_are_refused(knowledge):
    """A float inside a milestone row is refused too."""
    bad_row = row("100")  # a valid row ...
    bad_row["percent"] = 100.0  # ... with a float percentage
    with pytest.raises(TypeError, match="milestones.percent"):  # the message names the cell
        run(knowledge, payment_type="milestones", milestones=[bad_row])  # evaluate


# ---------------------------------------------------------------------------
# 3. The valid project
# ---------------------------------------------------------------------------

def test_valid_project_has_no_errors(knowledge):
    """The P1-like project (handoff E1): no errors, six clauses, only W_CONSUMER."""
    result = run(knowledge)  # nothing changed
    assert result["errors"] == []  # no error
    assert result["can_generate"] is True  # "Generate" allowed
    assert clause_ids(result) == ["PRICE_FIXED", "PAYMENT_ON_COMPLETION", "ACCEPTANCE_PROTOCOL", "DEFECTS_STANDARD", "LIABILITY_LAW", "TERMINATION_LAW"]  # price, payment, termination
    assert rule_ids(result["warnings"]) == ["W_CONSUMER"]  # only the consumer warning


# ---------------------------------------------------------------------------
# 4. R_SCOPE (handoff App. C)
# ---------------------------------------------------------------------------

def test_r_scope_contract_date_before_2026(knowledge):
    """A contract date before 1 January 2026 is out of scope (scenario P7)."""
    result = run(knowledge, contract_date=date(2025, 12, 31))  # one day too early
    assert places(result["errors"], "R_SCOPE") == ["contract_date"]  # error at the date
    assert result["selected_clauses"] == []  # no clauses when there is an error (D17)


def test_r_scope_first_supported_day(knowledge):
    """1 January 2026 itself is inside the scope (handoff App. B: "on/after 2026-01-01")."""
    assert run(knowledge, contract_date=date(2026, 1, 1))["errors"] == []  # no error


def test_r_scope_other_work_category(knowledge):
    """work_category "other" is out of scope (law packet Task 4)."""
    result = run(knowledge, work_category="other")  # unsupported category
    assert places(result["errors"], "R_SCOPE") == ["work_category"]  # error at the category


def test_r_scope_reports_missing_scope_answers_not_r_required(knowledge):
    """Missing work_category or scope_confirmed are reported by R_SCOPE only (checked_by, D16)."""
    result = run(knowledge, work_category=None, scope_confirmed=None)  # both unanswered
    assert places(result["errors"], "R_SCOPE") == ["work_category", "scope_confirmed"]  # R_SCOPE twice
    assert "R_REQUIRED" not in rule_ids(result["errors"])  # no second message for the same gaps


def test_r_scope_scope_not_confirmed(knowledge):
    """scope_confirmed = false (an answered "no") is out of scope."""
    assert places(run(knowledge, scope_confirmed=False)["errors"], "R_SCOPE") == ["scope_confirmed"]  # error


# ---------------------------------------------------------------------------
# 5. R_REQUIRED (handoff App. C, checks.missing_required_fields)
# ---------------------------------------------------------------------------

def test_r_required_one_error_per_missing_field(knowledge):
    """Each missing required field gets its own R_REQUIRED entry (all at once)."""
    result = run(knowledge, client_name="", site_address=None)  # two gaps
    assert places(result["errors"], "R_REQUIRED") == ["client_name", "site_address"]  # one entry each


def test_r_required_vat_treatment(knowledge):
    """A missing vat_treatment is reported (scenario P10; missing in the topic 1 flowchart)."""
    assert places(run(knowledge, vat_treatment=None)["errors"], "R_REQUIRED") == ["vat_treatment"]  # error


def test_r_required_missing_contract_date_is_not_r_scope(knowledge):
    """A missing date is R_REQUIRED; only a date before 2026 is R_SCOPE (D16)."""
    result = run(knowledge, contract_date=None)  # no date
    assert rule_ids(result["errors"]) == ["R_REQUIRED"]  # only R_REQUIRED


def test_r_required_answer_not_allowed(knowledge):
    """An enum answer that is not in allowed_values is reported (handoff App. C: "unsupported enum")."""
    assert places(run(knowledge, price_type="cheap")["errors"], "R_REQUIRED") == ["price_type"]  # error


def test_r_required_optional_fields_may_stay_empty(knowledge):
    """Optional fields (exclusions, annex register) may be empty (law packet Task 5)."""
    result = run(knowledge, exclusions_and_client_supplies="", annex_register=[])  # both empty
    assert result["errors"] == []  # no error


def test_r_required_incomplete_annex_row(knowledge):
    """An annex row without a date is an error, although the annex list itself is optional."""
    annex = [{"title": "Bathroom specification", "date": None, "revision": "A"}]  # date missing
    assert places(run(knowledge, annex_register=annex)["errors"], "R_REQUIRED") == ["annex_register"]  # error


# ---------------------------------------------------------------------------
# 6. R_PRICE (handoff App. C)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("price", ["0", "-1"])  # zero and negative prices
def test_r_price_price_not_positive(knowledge, price):
    """A price of zero or below is an error at contract_price (scenario P5)."""
    assert places(run(knowledge, contract_price=Decimal(price))["errors"], "R_PRICE") == ["contract_price"]  # error


def test_r_price_missing_price_is_r_required_only(knowledge):
    """A missing price is reported once, by R_REQUIRED, not also by R_PRICE (D16)."""
    result = run(knowledge, contract_price=None)  # no price
    assert rule_ids(result["errors"]) == ["R_REQUIRED"]  # only R_REQUIRED
    assert places(result["errors"], "R_REQUIRED") == ["contract_price"]  # at the price


@pytest.mark.parametrize("basis", [None, "", "   "])  # missing, empty, only spaces
def test_r_price_estimate_without_basis(knowledge, basis):
    """An estimate without a pricing basis is R_PRICE at estimate_basis, not R_REQUIRED (scenario P4, D16)."""
    result = run(knowledge, price_type="estimate", estimate_basis=basis)  # estimate, no basis
    assert rule_ids(result["errors"]) == ["R_PRICE"]  # only R_PRICE
    assert places(result["errors"], "R_PRICE") == ["estimate_basis"]  # at the basis


# ---------------------------------------------------------------------------
# 7. R_PAY (handoff App. B and C, law packet Task 9, checks.milestone_problems)
# ---------------------------------------------------------------------------

def test_r_pay_valid_schedules(knowledge):
    """Valid schedules give no error: 20/40/40 and a single 100 % milestone (D22)."""
    assert run(knowledge, payment_type="milestones", milestones=[row("20"), row("40"), row("40")])["errors"] == []  # 3 rows
    assert run(knowledge, payment_type="milestones", milestones=[row("100")])["errors"] == []  # 1 row


@pytest.mark.parametrize(  # one invalid schedule per case
    "rows",  # name of the value
    [  # the cases (each one is invalid for exactly one reason where possible)
        pytest.param([], id="no rows"),  # App. C: "Milestones missing"
        pytest.param([row("30"), row("30"), row("30")], id="total 90 (E4, P3)"),  # sum is not 100
        pytest.param([row("49.99"), row("50")], id="total 99.99 (REF07)"),  # sum is not 100
        pytest.param([row("50", name=""), row("50")], id="empty name"),  # App. B: non-empty
        pytest.param([row("50", trigger="  "), row("50")], id="empty trigger"),  # App. B: non-empty
        pytest.param([row("0"), row("100")], id="percent zero"),  # App. B: > 0
        pytest.param([row("150"), row("-50")], id="percent above 100"),  # App. B: <= 100
        pytest.param([row("33.333"), row("66.667")], id="three decimals"),  # D22: at most 2 decimals
        pytest.param([row("50", days=-1), row("50")], id="negative days"),  # App. B: >= 0
        pytest.param([row("50", days=Decimal("1.5")), row("50")], id="days not a whole number"),  # App. B: whole number
        pytest.param([row("50", advance=None), row("50")], id="advance unanswered"),  # law packet Task 9
    ],  # end of the cases
)  # end of parametrize
def test_r_pay_invalid_schedules(knowledge, rows):
    """Every kind of invalid milestone schedule is R_PAY at milestones, never R_REQUIRED (D16)."""
    result = run(knowledge, payment_type="milestones", milestones=rows)  # milestone payments with these rows
    assert rule_ids(result["errors"]) == ["R_PAY"]  # only R_PAY
    assert places(result["errors"], "R_PAY") == ["milestones"]  # at the milestone table


def test_r_pay_instalment_not_positive_after_rounding(knowledge):
    """CHF 0.01 split 50/50 would give an instalment of CHF 0.00 (law packet Task 9)."""
    result = run(knowledge, contract_price=Decimal("0.01"), payment_type="milestones", milestones=[row("50"), row("50")])  # tiny price
    assert rule_ids(result["errors"]) == ["R_PAY"]  # R_PAY


def test_r_pay_skips_amount_check_when_price_is_invalid(knowledge):
    """With price 0 only R_PRICE fires; R_PAY does not add a second message about amounts (D16)."""
    result = run(knowledge, contract_price=Decimal("0"), payment_type="milestones", milestones=[row("50"), row("50")])  # price 0
    assert rule_ids(result["errors"]) == ["R_PRICE"]  # only R_PRICE


# ---------------------------------------------------------------------------
# 8. W_PRICE and W_CONSUMER (handoff App. C, decisions D18-D20)
# ---------------------------------------------------------------------------

def test_w_price_estimate(knowledge):
    """An estimate gives W_PRICE at price_type with the estimate message (law packet Task 9)."""
    result = run(knowledge, price_type="estimate", estimate_basis="Hourly rate")  # valid estimate
    warning = [w for w in result["warnings"] if w["rule_id"] == "W_PRICE"]  # the W_PRICE entries
    assert len(warning) == 1 and warning[0]["field"] == "price_type"  # one, at the price type
    assert warning[0]["message"].startswith("The price is approximate, not a fixed ceiling.")  # estimate wording


def test_w_price_advance(knowledge):
    """An advance milestone gives W_PRICE at milestones with the advance message."""
    result = run(knowledge, payment_type="milestones", milestones=[row("20", advance=True), row("80")])  # first row advance
    warning = [w for w in result["warnings"] if w["rule_id"] == "W_PRICE"]  # the W_PRICE entries
    assert len(warning) == 1 and warning[0]["field"] == "milestones"  # one, at the milestones
    assert warning[0]["message"].startswith("This payment is due before its corresponding work is performed.")  # advance wording


def test_w_price_both_cases_are_shown(knowledge):
    """Estimate and advance together give two W_PRICE entries (D20, scenario P6)."""
    result = run(knowledge, price_type="estimate", estimate_basis="Hourly rate",  # estimate ...
                 payment_type="milestones", milestones=[row("20", advance=True), row("80")])  # ... with an advance
    assert places(result["warnings"], "W_PRICE") == ["price_type", "milestones"]  # both reasons


def test_w_price_not_for_fixed_price_without_advance(knowledge):
    """Fixed price, payment on delivery: no W_PRICE."""
    assert "W_PRICE" not in rule_ids(run(knowledge)["warnings"])  # the valid project


def test_w_price_not_from_stale_milestones(knowledge):
    """An advance in old, inactive milestones does not trigger W_PRICE (law packet REF10)."""
    result = run(knowledge, milestones=[row("100", advance=True)])  # payment stays on delivery
    assert "W_PRICE" not in rule_ids(result["warnings"])  # ignored


def test_w_consumer_always_shown_also_with_errors(knowledge):
    """W_CONSUMER is shown for every project, even when there are errors (D18, D19)."""
    result = run(knowledge, contract_price=Decimal("0"))  # an error
    assert "W_CONSUMER" in rule_ids(result["warnings"])  # still shown
    consumer = [w for w in result["warnings"] if w["rule_id"] == "W_CONSUMER"][0]  # the entry
    assert consumer["category"] == "LAW" and consumer["citations"] == ["UWG_8"]  # law packet page 12


# ---------------------------------------------------------------------------
# 9. SEL_ rules (handoff App. C)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(  # the four combinations of price type and payment type
    "price_type, payment_type, expected",  # names of the three values
    [  # the cases
        ("fixed", "on_completion", ["PRICE_FIXED", "PAYMENT_ON_COMPLETION", "ACCEPTANCE_PROTOCOL", "DEFECTS_STANDARD", "LIABILITY_LAW", "TERMINATION_LAW"]),  # SEL_PRICE_FIXED + SEL_PAYMENT_ON_COMPLETION
        ("fixed", "milestones", ["PRICE_FIXED", "PAYMENT_MILESTONE", "ACCEPTANCE_PROTOCOL", "DEFECTS_STANDARD", "LIABILITY_LAW", "TERMINATION_LAW"]),  # SEL_PRICE_FIXED + SEL_PAYMENT_MILESTONE
        ("estimate", "on_completion", ["PRICE_ESTIMATE", "PAYMENT_ON_COMPLETION", "ACCEPTANCE_PROTOCOL", "DEFECTS_STANDARD", "LIABILITY_LAW", "TERMINATION_LAW"]),  # SEL_PRICE_ESTIMATE + ...
        ("estimate", "milestones", ["PRICE_ESTIMATE", "PAYMENT_MILESTONE", "ACCEPTANCE_PROTOCOL", "DEFECTS_STANDARD", "LIABILITY_LAW", "TERMINATION_LAW"]),  # both "other" variants
    ],  # end of the cases
)  # end of parametrize
def test_sel_rules_select_one_price_and_one_payment_clause(knowledge, price_type, payment_type, expected):
    """Each SEL_ rule selects its clause; there is always exactly one price and one payment clause."""
    result = run(knowledge, price_type=price_type, estimate_basis="Hourly rate",  # the price answers
                 payment_type=payment_type, milestones=[row("50"), row("50")])  # the payment answers
    assert clause_ids(result) == expected  # the right clauses, price first
    assert [r["selection_rule_id"] for r in result["selected_clauses"]] == ["SEL_" + c for c in expected]  # the reason


def test_no_clauses_when_there_is_an_error(knowledge):
    """With an input error, steps 3 to 5 are skipped and no clause is selected (D17)."""
    result = run(knowledge, client_name="")  # one error
    assert result["can_generate"] is False and result["selected_clauses"] == []  # blocked, nothing selected


# ---------------------------------------------------------------------------
# 10. Step 4 (unfilled gap) and step 5 (R_CROSS)
# ---------------------------------------------------------------------------

def test_unfilled_gap_is_reported_as_r_required(knowledge):
    """If a gap cannot be filled, R_REQUIRED blocks generation (handoff App. C)."""
    changed = copy.deepcopy(knowledge)  # change a copy, not the shared knowledge
    changed["fields"]["vat_treatment"]["required"] = False  # pretend vat_treatment were optional
    result = evaluate({**valid_answers(), "vat_treatment": None}, changed)  # step 1 passes, but {vat_treatment_text} cannot be built
    assert places(result["errors"], "R_REQUIRED") == ["vat_treatment"]  # reported at the answer that chooses the text
    assert result["can_generate"] is False  # blocked


def test_r_cross_two_price_clauses(knowledge):
    """A data mistake that selects two price clauses is caught by R_CROSS (D24)."""
    changed = copy.deepcopy(knowledge)  # change a copy
    changed["rules"]["SEL_PRICE_ESTIMATE"]["when"] = {"field": "price_type", "op": "equals", "value": "fixed"}  # typo in the data
    result = evaluate(valid_answers(), changed)  # fixed price: both price clauses are selected
    assert places(result["errors"], "R_CROSS") == ["price_clause"]  # the price slot is over-filled
    assert result["can_generate"] is False  # blocked


def test_r_cross_no_payment_clause(knowledge):
    """A data mistake that selects no payment clause is caught by R_CROSS."""
    changed = copy.deepcopy(knowledge)  # change a copy
    changed["rules"]["SEL_PAYMENT_ON_COMPLETION"]["when"] = {"field": "payment_type", "op": "equals", "value": "milestones"}  # typo
    result = evaluate(valid_answers(), changed)  # payment on delivery: no payment clause any more
    assert places(result["errors"], "R_CROSS") == ["payment_clause"]  # the payment slot is empty


def test_unknown_check_name_is_refused(knowledge):
    """A check named in rules.yaml that checks.py does not have stops the engine with a clear message."""
    changed = copy.deepcopy(knowledge)  # change a copy
    changed["rules"]["R_PAY"]["cases"][0]["check"] = "milestone_problemz"  # typo in the check name
    with pytest.raises(ValueError, match="milestone_problemz"):  # the message names the check
        evaluate(valid_answers(), changed)  # evaluate


# ---------------------------------------------------------------------------
# 11. The result and the review records (handoff App. C, decisions D27, D28)
# ---------------------------------------------------------------------------

def test_all_errors_are_shown_at_once(knowledge):
    """Several input errors are all reported in one run, each at its own field."""
    result = run(knowledge, contract_date=date(2025, 6, 1), client_name="", contract_price=Decimal("0"),  # three errors ...
                 payment_type="milestones", milestones=[row("30"), row("30"), row("30")])  # ... and a fourth
    assert rule_ids(result["errors"]) == ["R_SCOPE", "R_REQUIRED", "R_PRICE", "R_PAY"]  # all four, in rule order


def test_messages_come_from_rules_yaml(knowledge):
    """The engine shows exactly the message written in rules.yaml (no wording in the code)."""
    result = run(knowledge, contract_price=Decimal("0"))  # R_PRICE fires
    assert result["errors"][0]["message"] == knowledge["rules"]["R_PRICE"]["message"]  # same text


def test_result_has_the_agreed_parts(knowledge):
    """The result has exactly the six agreed parts (D27)."""
    result = run(knowledge)  # the valid project
    assert list(result) == ["can_generate", "law_version", "errors", "warnings", "selected_clauses", "ignored_fields"]  # D27
    assert result["law_version"] == "2026-10-01"  # from sources.yaml


def test_review_record_contains_what_the_handoff_asks_for(knowledge):
    """Review record of PAYMENT_MILESTONE in a P2-like project (handoff App. C "Review record")."""
    result = run(knowledge, payment_type="milestones", milestones=[row("20", advance=True), row("40"), row("40")])  # P2-like
    record = result["selected_clauses"][1]  # the payment clause
    assert record["clause_id"] == "PAYMENT_MILESTONE" and record["clause_version"] == "1.0"  # clause and version
    assert record["selection_rule_id"] == "SEL_PAYMENT_MILESTONE" and record["reason"]  # why it was selected
    assert list(record["input_values"]) == ["milestones", "contract_price", "price_type"]  # the answers it used
    assert [c["label"] for c in record["citations"]] == ["Art. 372 para. 1-2 CO", "Art. 374 CO"]  # article references
    assert record["citations"][0]["source_id"] == "S1" and record["citations"][0]["url"].startswith("https://")  # source
    assert record["law_version"] == "2026-10-01"  # law version
    assert record["warnings"] == ["W_PRICE"]  # the warning of the same topic; W_CONSUMER only at the top (D28)
    assert record["slot"] == "payment_clause" and record["position"] == 2  # where it goes


def test_court_decisions_of_the_fixed_price_clause(knowledge):
    """PRICE_FIXED cites the decisions on Art. 373 para. 2 CO, each with its own link (research document, section 6)."""
    record = run(knowledge)["selected_clauses"][0]  # the price clause of the valid project
    citations = {c["citation_id"]: c for c in record["citations"]}  # by ID
    assert list(citations) == ["CO_363", "CO_373_1_TO_3", "BGE_104_II_314", "BGE_113_II_513"]  # statute first, then decisions
    assert citations["BGE_104_II_314"]["url"] == "https://servat.unibe.ch/dfr/bge/c2104314.html"  # the decision's own link
    assert citations["BGE_104_II_314"]["source_id"] == "BGER" and citations["BGE_104_II_314"]["summary"]  # source and sentence
    assert "fedlex" in citations["CO_363"]["url"]  # a statute still links to the official text


def test_court_decisions_of_the_estimate_clause(knowledge):
    """PRICE_ESTIMATE cites the decisions on estimate overruns under Art. 375 CO."""
    record = run(knowledge, price_type="estimate", estimate_basis="Hourly rates")["selected_clauses"][0]  # the price clause
    assert [c["citation_id"] for c in record["citations"]] == ["CO_374", "CO_375_1_TO_2", "BGE_115_II_460", "BGER_4A_15_2011"]


def test_payment_clauses_cite_no_court_decision(knowledge):
    """The research document names no decision on Art. 372 CO, so payment clauses cite the statute only."""
    record = run(knowledge)["selected_clauses"][1]  # the payment clause of the valid project
    assert [c["citation_id"] for c in record["citations"]] == ["CO_372_1_TO_2"]  # no decision


def test_case_citations_only_appear_on_their_own_case(knowledge):
    """W_PRICE: the decisions on estimates are shown at the estimate warning, not at the advance warning."""
    result = run(knowledge, price_type="estimate", estimate_basis="Hourly rates", payment_type="milestones",
                 milestones=[row("20", advance=True), row("80")])  # both W_PRICE cases fire
    estimate, advance = [w for w in result["warnings"] if w["rule_id"] == "W_PRICE"]  # in the order of rules.yaml
    assert estimate["citations"] == ["CO_374", "CO_375", "BGE_115_II_460", "BGER_4A_15_2011"]  # rule's plus the case's
    assert advance["citations"] == ["CO_374", "CO_375"]  # only the rule's own


def test_r_price_decision_only_at_the_missing_estimate_basis(knowledge):
    """R_PRICE: 4A_15/2011 is shown at the missing estimate basis, not at a price that is not positive."""
    result = run(knowledge, price_type="estimate", estimate_basis="", contract_price=Decimal("0"))  # both cases fire
    entries = {e["field"]: e for e in result["errors"] if e["rule_id"] == "R_PRICE"}  # by question
    assert entries["contract_price"]["citations"] == ["CO_374"]  # only the rule's own
    assert entries["estimate_basis"]["citations"] == ["CO_374", "BGER_4A_15_2011"]  # rule's plus the case's


# ---------------------------------------------------------------------------
# 12. Topic 5 "Termination" (handoff App. B, C, D and E7)
# ---------------------------------------------------------------------------

def with_grounds(knowledge, **changes):
    """Evaluate a valid project with special termination grounds, with some answers changed."""
    grounds = {"termination_reasons": True, "selected_termination_reasons": ["client_material_nonpayment"],  # one ground
               "cure_period_days": 30}  # a positive period
    return run(knowledge, **{**grounds, **changes})  # the grounds, overwritten by the changes


def test_no_special_grounds_selects_termination_law(knowledge):
    """termination_reasons = false: the statutory baseline, without any gap (App. C, E1)."""
    record = run(knowledge)["selected_clauses"][-1]  # the last clause
    assert record["clause_id"] == "TERMINATION_LAW" and record["selection_rule_id"] == "SEL_TERMINATION_LAW"  # clause and rule
    assert record["slot"] == "termination_clause" and record["position"] == 6  # the last of the six clauses
    assert record["text"].startswith("Before the Works are complete, the Client may terminate under Article 377 CO")  # App. D
    assert "{" not in record["text"]  # no gap left


def test_special_grounds_select_termination_for_cause(knowledge):
    """termination_reasons = true: the clause with the selected ground and the cure period (E7)."""
    result = with_grounds(knowledge)  # a valid project with one ground
    assert result["can_generate"] is True  # "Generate" allowed
    record = result["selected_clauses"][-1]  # the last clause
    assert record["clause_id"] == "TERMINATION_FOR_CAUSE"  # App. C
    assert "material breaches: the Client’s material failure to pay an amount properly due, subject to lawful payment defences." in record["text"]  # App. D
    assert "allow at least 30 calendar days after receipt to cure" in record["text"]  # the period
    assert "{" not in record["text"]  # no gap left


def test_both_grounds_are_joined_in_a_fixed_order(knowledge):
    """Two grounds: App. D phrases joined by "; ", independent of the order of the answers."""
    reasons = ["client_material_nonpayment", "contractor_material_nonperformance"]  # selected in the "wrong" order
    text = with_grounds(knowledge, selected_termination_reasons=reasons)["selected_clauses"][-1]["text"]  # the clause
    assert ("the Contractor’s material failure to perform the agreed Works; "  # first the Contractor's ground
            "the Client’s material failure to pay an amount properly due, subject to lawful payment defences.") in text  # then the Client's


@pytest.mark.parametrize(  # the ways special grounds can be unusable (App. C, E7)
    "reasons, days, expected",  # the answers and the fields R_TERM must report
    [  # the cases
        (["client_material_nonpayment"], None, ["cure_period_days"]),  # E7: no cure period
        (["client_material_nonpayment"], 0, ["cure_period_days"]),  # zero is not positive
        (["client_material_nonpayment"], -5, ["cure_period_days"]),  # negative
        ([], 30, ["selected_termination_reasons"]),  # no ground selected
        (None, 30, ["selected_termination_reasons"]),  # not answered
        ([], None, ["selected_termination_reasons", "cure_period_days"]),  # both problems
    ],  # end of the cases
)  # end of parametrize
def test_r_term_reports_unusable_grounds(knowledge, reasons, days, expected):
    """R_TERM blocks generation at each question with a problem; R_REQUIRED stays silent (D16)."""
    result = with_grounds(knowledge, selected_termination_reasons=reasons, cure_period_days=days)  # the changed answers
    assert places(result["errors"], "R_TERM") == expected  # reported at the right questions
    assert "R_REQUIRED" not in rule_ids(result["errors"])  # one problem = one error
    assert result["can_generate"] is False and result["selected_clauses"] == []  # blocked, no clauses (D17)


def test_unsupported_ground_is_stopped_when_the_gap_stays_open(knowledge):
    """The app only offers supported grounds; any other value leaves the gap open, so step 4 gives R_REQUIRED."""
    result = with_grounds(knowledge, selected_termination_reasons=["free_cancellation"])  # not possible in the app
    assert places(result["errors"], "R_REQUIRED") == ["selected_termination_reasons"]  # reported at the grounds
    assert result["can_generate"] is False  # blocked


def test_r_term_is_a_product_error(knowledge):
    """App. C: R_TERM has the basis "PRODUCT", so it asserts no statutory rule."""
    error = with_grounds(knowledge, cure_period_days=None)["errors"][0]  # the R_TERM entry
    assert error["rule_id"] == "R_TERM" and error["category"] == "PRODUCT" and error["citations"] == []  # PRODUCT, no citation


def test_termination_question_is_required(knowledge):
    """An unanswered termination question gives R_REQUIRED at that question (false would be an answered "no")."""
    assert places(run(knowledge, termination_reasons=None)["errors"], "R_REQUIRED") == ["termination_reasons"]  # App. B


def test_stale_grounds_are_ignored(knowledge):
    """termination_reasons = false: old grounds and an old invalid period cause no error (App. B "Inactive inputs")."""
    result = run(knowledge, termination_reasons=False, selected_termination_reasons=["client_material_nonpayment"],  # old ground
                 cure_period_days=0)  # old invalid period
    assert result["can_generate"] is True  # no R_TERM
    assert clause_ids(result)[-1] == "TERMINATION_LAW"  # still the statutory baseline
    assert set(result["ignored_fields"]) == {"selected_termination_reasons", "cure_period_days"}  # listed as ignored
    assert "W_CURE" not in rule_ids(result["warnings"])  # no special grounds, no cure warning


def test_w_cure_with_special_grounds(knowledge):
    """W_CURE warns at the cure period and allows generation (App. C, E7)."""
    result = with_grounds(knowledge)  # a valid project with one ground
    warning = [w for w in result["warnings"] if w["rule_id"] == "W_CURE"]  # the W_CURE entries
    assert [w["field"] for w in warning] == ["cure_period_days"]  # next to the cure period
    assert warning[0]["citations"] == ["CO_107_TO_108"]  # App. C: "CO 107–108"
    assert result["can_generate"] is True  # a warning does not block


def test_w_cure_is_also_shown_with_errors(knowledge):
    """Warnings are always computed (D18), so W_CURE also appears next to R_TERM."""
    result = with_grounds(knowledge, cure_period_days=None)  # special grounds without a period
    assert "W_CURE" in rule_ids(result["warnings"]) and "R_TERM" in rule_ids(result["errors"])  # both


def test_r_cross_no_termination_clause(knowledge):
    """A data mistake that selects no termination clause is caught by R_CROSS (App. C: exactly one variant)."""
    changed = copy.deepcopy(knowledge)  # change a copy
    changed["rules"]["SEL_TERMINATION_LAW"]["when"] = {"field": "termination_reasons", "op": "equals", "value": True}  # data mistake
    error = evaluate(valid_answers(), changed)["errors"][0]  # no termination clause is selected any more
    assert error["rule_id"] == "R_CROSS" and error["field"] == "termination_clause"  # the slot is empty
    assert error["category"] == "PRODUCT"  # counting clauses is a PRODUCT check (D24)


def test_court_decision_of_the_termination_clauses(knowledge):
    """Both clauses reserve the same articles, so both show the same legal basis, ending with BGE 117 II 273."""
    law = run(knowledge)["selected_clauses"][-1]["citations"]  # citations of TERMINATION_LAW
    cause = with_grounds(knowledge)["selected_clauses"][-1]["citations"]  # citations of TERMINATION_FOR_CAUSE
    assert [c["citation_id"] for c in law] == ["CO_377", "CO_107_TO_109", "CO_366_1", "CO_373_2", "CO_375", "CO_376",  # the articles
                                               "CO_378", "CO_379", "BGE_117_II_273"]  # and the decision
    assert cause == law  # the same list, because the clause text reserves the same articles
    decision = law[-1]  # the decision
    assert decision["source_id"] == "BGER" and decision["url"] == "https://servat.unibe.ch/dfr/bge/c2117273.html"  # source and its link


def test_warnings_of_the_topic_are_in_the_review_record(knowledge):
    """A review record lists the warnings of its own topic only (D28)."""
    result = with_grounds(knowledge, price_type="estimate", estimate_basis="Hourly rate")  # both topics warn
    price, termination = result["selected_clauses"][0], result["selected_clauses"][-1]  # the first and the last record
    assert price["warnings"] == ["W_PRICE"]  # topic 1
    assert termination["warnings"] == ["W_CURE"]  # topic 5


def test_input_values_of_termination_for_cause(knowledge):
    """The review record stores the answers the clause used (App. C "actual input values")."""
    record = with_grounds(knowledge)["selected_clauses"][-1]  # TERMINATION_FOR_CAUSE
    assert record["input_values"] == {"selected_termination_reasons": ["client_material_nonpayment"], "cure_period_days": 30}  # the answers


def test_review_record_text_is_filled(knowledge):
    """The selected clause texts have every gap filled."""
    result = run(knowledge)  # the valid project
    price_text = result["selected_clauses"][0]["text"]  # the PRICE_FIXED text
    assert price_text.startswith("The fixed price for the Works is CHF 100,000.00. This amount includes applicable VAT.")  # filled
    assert "{" not in price_text  # no gap left


# ---------------------------------------------------------------------------
# 13. Topics 2-4: completion date and delay penalty, acceptance and defects, liability
# ---------------------------------------------------------------------------

def with_penalty(knowledge, **changes):
    """Evaluate a valid project with a binding date and a capped penalty (handoff E2), with some answers changed."""
    penalty = {"completion_date": date(2027, 6, 30), "completion_definition": "All agreed Works ready for handover",  # binding date
               "delay_penalty": True, "penalty_amount": Decimal("700"), "penalty_period": "week",  # CHF 700 per week
               "penalty_cap": Decimal("5")}  # maximum 5 %
    return run(knowledge, **{**penalty, **changes})  # the penalty answers, overwritten by the changes


def record_of(result, clause_id):
    """Return the review record of one selected clause."""
    return next(record for record in result["selected_clauses"] if record["clause_id"] == clause_id)  # the first match


def citation_ids(result, clause_id):
    """Return the citation IDs of one selected clause."""
    return [citation["citation_id"] for citation in record_of(result, clause_id)["citations"]]  # in YAML order


def test_e1_has_acceptance_defects_and_statutory_liability(knowledge):
    """E1: no date and no penalty, so section 6 stays empty; the defects clause names the notice contact."""
    result = run(knowledge)  # the valid project
    assert "DEADLINE_FIXED" not in clause_ids(result)  # no binding date
    assert not any(clause_id.startswith("PENALTY_") for clause_id in clause_ids(result))  # no penalty
    assert "be sent to Bau AG, Werkweg 5, 3000 Bern;" in record_of(result, "DEFECTS_STANDARD")["text"]  # contact filled


def test_e2_capped_penalty(knowledge):
    """E2: CHF 700 per week, maximum 5 %: DEADLINE_FIXED and PENALTY_CAPPED; the base is the fixed price."""
    result = with_penalty(knowledge)  # E2
    assert result["can_generate"] is True  # no error
    assert clause_ids(result)[2:4] == ["DEADLINE_FIXED", "PENALTY_CAPPED"]  # right after price and payment
    text = record_of(result, "PENALTY_CAPPED")["text"]  # the filled clause
    assert "by 30 June 2027, as validly extended" in text  # the date
    assert "CHF 700.00 per calendar week of delay" in text  # amount and penalty_period_text
    assert "limited to 5% of the agreed base of CHF 100,000.00" in text  # App. B: base derived from the contract price
    assert "{" not in text  # no gap left
    assert rule_ids(result["warnings"]) == ["W_CONSUMER"]  # a maximum is set, so no W_PEN


def test_penalty_day_rate(knowledge):
    """A day rate prints "calendar day" (App. D penalty_period_text)."""
    text = record_of(with_penalty(knowledge, penalty_period="day", penalty_amount=Decimal("150")), "PENALTY_CAPPED")["text"]  # day
    assert "CHF 150.00 per calendar day of delay" in text  # amount and period


def test_uncapped_penalty_gives_w_pen(knowledge):
    """No maximum: PENALTY_UNCAPPED and W_PEN with CO 163 and BGE 114 II 264 (App. C)."""
    result = with_penalty(knowledge, penalty_cap=None)  # no maximum
    assert "No contractual maximum is agreed." in record_of(result, "PENALTY_UNCAPPED")["text"]  # App. D
    warning = [w for w in result["warnings"] if w["rule_id"] == "W_PEN"]  # the W_PEN entries
    assert [w["field"] for w in warning] == ["penalty_cap"]  # next to the maximum
    assert warning[0]["citations"] == ["CO_163", "BGE_114_II_264"]  # legal basis
    assert result["can_generate"] is True  # a warning does not block


def test_e3_penalty_without_date_is_r_pen_01(knowledge):
    """E3: a penalty without a date is R_PEN_01, labelled PRODUCT, not "Swiss law requires a written date"."""
    result = with_penalty(knowledge, completion_date=None)  # no date
    error = [e for e in result["errors"] if e["rule_id"] == "R_PEN_01"]  # the R_PEN_01 entries
    assert [e["field"] for e in error] == ["completion_date"]  # next to the date
    assert error[0]["category"] == "PRODUCT" and "not a statement that Swiss law requires" in error[0]["message"]  # E3
    assert result["can_generate"] is False  # blocked


@pytest.mark.parametrize(  # App. C R_PEN_02: amount, period, cap, base
    "changes, expected",  # the changed answers and the fields R_PEN_02 must report
    [  # the cases
        ({"penalty_amount": None}, ["penalty_amount"]),  # no amount
        ({"penalty_amount": Decimal("0")}, ["penalty_amount"]),  # amount 0
        ({"penalty_period": None}, ["penalty_period"]),  # no period
        ({"penalty_cap": Decimal("0")}, ["penalty_cap"]),  # App. B: 0 never means "uncapped"
        ({"penalty_cap": Decimal("-1")}, ["penalty_cap"]),  # negative maximum
        ({"price_type": "estimate", "estimate_basis": "Hourly rates"}, ["penalty_cap_basis_chf"]),  # capped estimate, no base
        ({"price_type": "estimate", "estimate_basis": "Hourly rates", "penalty_cap_basis_chf": Decimal("0")},  # base 0
         ["penalty_cap_basis_chf"]),  # reported at the base
    ],  # end of the cases
)  # end of parametrize
def test_r_pen_02(knowledge, changes, expected):
    """R_PEN_02 blocks at the right question; R_REQUIRED stays silent (D16)."""
    result = with_penalty(knowledge, **changes)  # the changed answers
    assert places(result["errors"], "R_PEN_02") == expected  # the right question
    assert "R_REQUIRED" not in rule_ids(result["errors"])  # one problem = one error


def test_capped_estimate_uses_its_own_base(knowledge):
    """For an estimate the base is entered by the user (App. B)."""
    result = with_penalty(knowledge, price_type="estimate", estimate_basis="Hourly rates",  # an estimate
                          penalty_cap_basis_chf=Decimal("80000"))  # with its own base
    assert result["can_generate"] is True  # no error
    assert "limited to 5% of the agreed base of CHF 80,000.00" in record_of(result, "PENALTY_CAPPED")["text"]  # its base


def test_date_without_penalty_selects_only_deadline_fixed(knowledge):
    """A date without a penalty gives DEADLINE_FIXED only; old penalty answers are ignored (E8)."""
    result = with_penalty(knowledge, delay_penalty=False)  # date, but no penalty
    assert "DEADLINE_FIXED" in clause_ids(result)  # the date clause
    assert not any(clause_id.startswith("PENALTY_") for clause_id in clause_ids(result))  # no penalty clause
    assert set(result["ignored_fields"]) == {"penalty_amount", "penalty_period", "penalty_cap"}  # ignored


def test_r_date_completion_before_contract_date(knowledge):
    """App. C R_DATE: a completion date before the contract date (1 November 2026) is blocked."""
    result = with_penalty(knowledge, completion_date=date(2026, 10, 1))  # a month before the contract
    assert places(result["errors"], "R_DATE") == ["completion_date"]  # next to the date


def test_r_date_allows_the_contract_date_itself(knowledge):
    """The same day is not "before" the contract date."""
    assert "R_DATE" not in rule_ids(with_penalty(knowledge, completion_date=date(2026, 11, 1))["errors"])  # same day


def test_r_date_date_without_definition(knowledge):
    """App. C R_DATE: a date without a completion definition is blocked by R_DATE, not R_REQUIRED (D16)."""
    result = with_penalty(knowledge, completion_definition="")  # no definition
    assert places(result["errors"], "R_DATE") == ["completion_definition"]  # next to the definition
    assert "R_REQUIRED" not in rule_ids(result["errors"])  # one problem = one error


@pytest.mark.parametrize("field", ["delay_penalty", "defect_notice_contact", "liability_limit"])  # App. B: always required
def test_topic_2_to_4_questions_are_required(knowledge, field):
    """An unanswered question of topics 2-4 gives R_REQUIRED at that question."""
    assert places(run(knowledge, **{field: None})["errors"], "R_REQUIRED") == [field]  # reported where it is missing


def test_liability_cap(knowledge):
    """liability_limit = true: LIABILITY_CAP with the amount, its decisions, and W_LIAB (App. C)."""
    result = run(knowledge, liability_limit=True, liability_cap_amount=Decimal("100000"))  # a cap of CHF 100,000
    assert result["can_generate"] is True  # a warning does not block
    assert "is limited to CHF 100,000.00." in record_of(result, "LIABILITY_CAP")["text"]  # the amount
    assert citation_ids(result, "LIABILITY_CAP") == ["CO_100", "CO_101", "BGE_95_II_43", "BGER_4C_92_2007"]  # legal basis
    warning = [w for w in result["warnings"] if w["rule_id"] == "W_LIAB"]  # the W_LIAB entries
    assert [w["field"] for w in warning] == ["liability_limit"]  # next to the question
    assert warning[0]["citations"] == ["CO_100", "UWG_8"]  # App. C: "CO 100(2); UWG 8"


@pytest.mark.parametrize("amount", [None, Decimal("0"), Decimal("-100")])  # missing, zero, negative
def test_r_liab_value(knowledge, amount):
    """App. C R_LIAB_VALUE: a cap without a positive amount is blocked; W_LIAB is still shown (D18)."""
    result = run(knowledge, liability_limit=True, liability_cap_amount=amount)  # the changed amount
    assert places(result["errors"], "R_LIAB_VALUE") == ["liability_cap_amount"]  # next to the amount
    assert "R_REQUIRED" not in rule_ids(result["errors"])  # one problem = one error (D16)
    assert "W_LIAB" in rule_ids(result["warnings"])  # warnings are always computed


def test_stale_cap_amount_is_ignored(knowledge):
    """liability_limit = false: an old cap amount is ignored and there is no W_LIAB."""
    result = run(knowledge, liability_limit=False, liability_cap_amount=Decimal("50000"))  # old amount
    assert "LIABILITY_LAW" in clause_ids(result) and result["ignored_fields"] == ["liability_cap_amount"]  # ignored
    assert "W_LIAB" not in rule_ids(result["warnings"])  # no cap, no warning


def test_court_decisions_of_topics_2_to_4(knowledge):
    """The decisions from the research documents are on the clauses they interpret."""
    result = with_penalty(knowledge)  # date, capped penalty, statutory liability
    assert citation_ids(result, "PENALTY_CAPPED")[-2:] == ["BGE_114_II_264", "BGE_97_II_350"]  # CO 163(3) and 160(2)
    assert citation_ids(result, "ACCEPTANCE_PROTOCOL")[-1] == "BGE_97_II_350"  # acceptance and penalty reservation
    assert citation_ids(result, "LIABILITY_LAW")[-1] == "BGE_95_II_43"  # auxiliary persons
    assert citation_ids(result, "DEFECTS_STANDARD") == ["CO_366_2", "CO_367", "CO_368", "CO_369", "CO_370", "CO_371"]  # no decision
    decision = record_of(result, "PENALTY_CAPPED")["citations"][-2]  # BGE 114 II 264
    assert decision["source_id"] == "BGER" and decision["url"] == "https://www.servat.unibe.ch/dfr/bge/c2114264.html"  # its link
