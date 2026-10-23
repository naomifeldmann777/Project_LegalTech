"""test_engine.py - automatic tests for engine.py and checks.py.

What this file is for:
    It tests the rule engine piece by piece, with at least one test per rule
    (AI_PROMPT step 11): R_SCOPE, R_REQUIRED, R_PRICE, R_PAY, W_PRICE, W_CONSUMER,
    the four SEL_ rules and R_CROSS. It also tests the condition operators, step 0
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
    """Answers for fields that are not in parameters.yaml (e.g. old penalty values) are ignored."""
    result = run(knowledge, delay_penalty=False, penalty_cap=Decimal("5"))  # topic 2 fields, not in iteration 1
    assert result["ignored_fields"] == ["delay_penalty", "penalty_cap"]  # listed as ignored
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
    """The P1-like project: no errors, two clauses, only W_CONSUMER."""
    result = run(knowledge)  # nothing changed
    assert result["errors"] == []  # no error
    assert result["can_generate"] is True  # "Generate" allowed
    assert clause_ids(result) == ["PRICE_FIXED", "PAYMENT_ON_COMPLETION"]  # price first, then payment
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
        ("fixed", "on_completion", ["PRICE_FIXED", "PAYMENT_ON_COMPLETION"]),  # SEL_PRICE_FIXED + SEL_PAYMENT_ON_COMPLETION
        ("fixed", "milestones", ["PRICE_FIXED", "PAYMENT_MILESTONE"]),  # SEL_PRICE_FIXED + SEL_PAYMENT_MILESTONE
        ("estimate", "on_completion", ["PRICE_ESTIMATE", "PAYMENT_ON_COMPLETION"]),  # SEL_PRICE_ESTIMATE + ...
        ("estimate", "milestones", ["PRICE_ESTIMATE", "PAYMENT_MILESTONE"]),  # both "other" variants
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


def test_review_record_text_is_filled(knowledge):
    """The selected clause texts have every gap filled."""
    result = run(knowledge)  # the valid project
    price_text = result["selected_clauses"][0]["text"]  # the PRICE_FIXED text
    assert price_text.startswith("The fixed price for the Works is CHF 100,000.00. This amount includes applicable VAT.")  # filled
    assert "{" not in price_text  # no gap left
