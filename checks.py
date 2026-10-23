"""checks.py - the special checks that rules.yaml refers to by name.

What this file is for:
    A condition in rules.yaml looks at one answer at a time, for example
    "contract_price at_most 0". Four rules need more than that: they have to go
    through all fields, add up the milestone percentages, or count the selected
    clauses. Those four checks are small Python functions, all listed here in one
    place (AI_PROMPT section 11). A rule names its check in rules.yaml:
        cases:
          - when: {field: payment_type, op: equals, value: milestones}
            check: milestone_problems

How it fits into the project:
    engine.py looks up the name in CHECKS (end of this file) and calls the function.
    Every check works the same way:
      - it receives answers, knowledge and selected (see below)
      - it returns a list of the places that have a problem (field IDs, or slot
        IDs for R_CROSS); an EMPTY list means "no problem", so the rule does not fire
    The messages are NOT here; they stay in rules.yaml.
    Parameters of every check:
      answers   the ACTIVE answers only: the engine removes inactive fields and
                adds active but unanswered fields with the value None, so
                "field_id in answers" means "this field is active"
      knowledge the result of data_loader.load_knowledge()
      selected  the clause IDs selected so far (only used by selection_cardinality;
                the other checks run before clauses are selected and ignore it)
    No Streamlit, no wording, no clause selection here.

Which documents it implements:
    - Handoff App. B: required fields, allowed answers, milestone records
    - Handoff App. C: R_REQUIRED, R_PAY, W_PRICE (advance), R_CROSS (cardinality)
    - Law packet Task 9 (R_PAY also covers unanswered advance and positive amounts)
    - Decisions D16 (checked_by), D22 (milestones), D24 (cardinality per slot), D42
"""

from decimal import Decimal  # exact numbers: percentages and amounts are compared exactly

from placeholders import milestone_amounts  # the same rounding rule as in the contract (D23)


HUNDRED = Decimal("100")  # the milestone percentages must add up to exactly 100
CENT = Decimal("0.01")  # percentages may have at most 2 decimals (D22)


# ---------------------------------------------------------------------------
# Helper (also used by engine.py for the operators is_empty / is_filled)
# ---------------------------------------------------------------------------

def is_empty(value):
    """Return True if an answer counts as "not answered".

    Empty means: None, a text with only spaces, or an empty list.
    False is NOT empty: it is an answered "no" (handoff App. B).
    Examples: is_empty(None) -> True, is_empty("  ") -> True, is_empty(False) -> False
    """
    if value is None:  # never answered
        return True  # empty
    if isinstance(value, str):  # text
        return value.strip() == ""  # empty if only spaces
    if isinstance(value, (list, dict)):  # a table or a record
        return len(value) == 0  # empty if it has no rows
    return False  # numbers, dates and True/False are answers


# ---------------------------------------------------------------------------
# R_REQUIRED (handoff App. C): active required field missing or not allowed
# ---------------------------------------------------------------------------

def missing_required_fields(answers, knowledge, selected):
    """Return the IDs of active fields that are missing, not allowed, or incomplete.

    For every active field (every key in answers):
      - fields with "checked_by" are skipped; another rule reports them (D16)
      - a required field without an answer is reported
      - an enum answer that is not in allowed_values is reported
      - a list with a row whose required column is empty is reported (e.g. an
        annex without a date), even if the list itself is optional

    Example: client_name empty and site_address empty -> ["client_name", "site_address"]
    """
    problems = []  # the field IDs with a problem, in questionnaire order
    for field_id, value in answers.items():  # each active field and its answer
        field = knowledge["fields"].get(field_id)  # its definition from parameters.yaml
        if field is None or field.get("checked_by"):  # unknown, or reported by another rule (D16)
            continue  # nothing to do here
        if is_empty(value):  # no answer
            if field["required"]:  # but an answer is needed
                problems.append(field_id)  # report the missing answer
            continue  # an empty answer cannot be checked further
        if field["type"] == "enum" and value not in _allowed_values(field):  # e.g. price_type "cheap"
            problems.append(field_id)  # report the answer that is not allowed
        elif field["type"] == "list" and not _rows_complete(value, field["columns"]):  # a row with an empty cell
            problems.append(field_id)  # report the incomplete table
    return problems  # empty list = no problem


def _allowed_values(field):
    """Return the stored values an enum field allows, e.g. {"fixed", "estimate"}."""
    return {option["value"] for option in field["allowed_values"]}  # the "value" of each option


def _rows_complete(rows, columns):
    """Return True if every row has an answer in every required column."""
    for row in rows:  # each row of the table
        for column in columns:  # each column of the table
            if column["required"] and is_empty(row.get(column["id"])):  # required cell without an answer
                return False  # the table is incomplete
    return True  # all required cells are filled


# ---------------------------------------------------------------------------
# R_PAY (handoff App. B and C, law packet Task 9): invalid milestone schedule
# ---------------------------------------------------------------------------

def milestone_problems(answers, knowledge, selected):
    """Return ["milestones"] if the milestone schedule is invalid, otherwise [].

    The schedule is invalid if (handoff App. B "Milestone records", law packet Task 9):
      - there is no row (D22: at least one milestone)
      - a row has an empty name or trigger, a percent that is not > 0 and <= 100
        or has more than 2 decimals (D22), invoice days that are not a whole
        number >= 0, or an unanswered advance
      - the percentages do not add up to exactly 100 (example: 30 + 30 + 30 = 90, E4)
      - an instalment would not be positive after rounding to cents
    The amount check is skipped while the price is missing or not positive,
    because R_REQUIRED or R_PRICE already report that (one problem = one error, D16).
    """
    rows = answers.get("milestones")  # the rows of the milestone table
    if is_empty(rows):  # no row at all
        return ["milestones"]  # App. C: "Milestones missing"
    if not all(_milestone_row_ok(row) for row in rows):  # at least one row is invalid
        return ["milestones"]  # report the table
    percents = [Decimal(row["percent"]) for row in rows]  # the percentages as Decimal
    if sum(percents) != HUNDRED:  # must add up to exactly 100 (App. B)
        return ["milestones"]  # e.g. 30 + 30 + 30 = 90 (scenario E4 / P3)
    price = answers.get("contract_price")  # the price the rows share
    if isinstance(price, Decimal) and price > 0:  # only if the price itself is valid
        if any(amount <= 0 for amount in milestone_amounts(price, percents)):  # an instalment of CHF 0.00 or less
            return ["milestones"]  # law packet: positive amounts after cent allocation
    return []  # the schedule is valid


def _milestone_row_ok(row):
    """Return True if one milestone row is complete and valid (handoff App. B)."""
    if not isinstance(row, dict):  # a row must be a record with named cells
        return False  # invalid
    if is_empty(row.get("name")) or is_empty(row.get("trigger")):  # App. B: non-empty text
        return False  # invalid
    percent = row.get("percent")  # the share of the price
    if isinstance(percent, bool) or not isinstance(percent, (Decimal, int)):  # must be a number (True is not one)
        return False  # invalid
    percent = Decimal(percent)  # the same type for every check below
    if not (0 < percent <= HUNDRED) or percent != percent.quantize(CENT):  # > 0, <= 100, at most 2 decimals
        return False  # invalid
    days = row.get("invoice_due_days")  # days to pay after the invoice
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:  # App. B: whole number >= 0
        return False  # invalid
    return isinstance(row.get("advance"), bool)  # advance must be answered true or false (law packet Task 9)


# ---------------------------------------------------------------------------
# W_PRICE, advance case (handoff App. C): an advance payment is agreed
# ---------------------------------------------------------------------------

def any_advance_milestone(answers, knowledge, selected):
    """Return ["milestones"] if at least one milestone is an advance, otherwise [].

    Example: rows 20 % (advance), 40 %, 40 % -> ["milestones"]
    """
    rows = answers.get("milestones") or []  # the rows, or none
    if any(isinstance(row, dict) and row.get("advance") is True for row in rows):  # one advance is enough
        return ["milestones"]  # the warning is shown next to the milestone table
    return []  # no advance payment


# ---------------------------------------------------------------------------
# R_CROSS, cardinality part (handoff App. C, decision D24): clauses per slot
# ---------------------------------------------------------------------------

def selection_cardinality(answers, knowledge, selected):
    """Return the slot IDs whose number of selected clauses is outside min..max.

    Each slot of clauses.yaml says how many clauses it needs, e.g. price_clause:
    min 1, max 1. With correct data this always returns []; it catches mistakes
    in the data files, such as two SEL_ rules that select clauses for the same slot.

    Example: PRICE_FIXED and PRICE_ESTIMATE both selected -> ["price_clause"]
    """
    counts = {slot_id: 0 for slot_id in knowledge["slots"]}  # start every slot at 0 clauses
    for clause_id in selected:  # each selected clause
        counts[knowledge["clauses"][clause_id]["slot"]] += 1  # count it in its slot
    problems = []  # slots with too few or too many clauses
    for slot_id, slot in knowledge["slots"].items():  # each slot with its min and max
        if not slot["min"] <= counts[slot_id] <= slot["max"]:  # outside the allowed range
            problems.append(slot_id)  # report the slot
    return problems  # empty list = every slot is filled correctly


# ---------------------------------------------------------------------------
# The list of all checks: name used in rules.yaml -> Python function
# ---------------------------------------------------------------------------

CHECKS = {
    "missing_required_fields": missing_required_fields,  # R_REQUIRED
    "milestone_problems": milestone_problems,  # R_PAY
    "any_advance_milestone": any_advance_milestone,  # W_PRICE (advance case)
    "selection_cardinality": selection_cardinality,  # R_CROSS (cardinality)
}  # a new check = a new function above + one line here
