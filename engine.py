"""engine.py - the rule engine: the user's answers go in, the result comes out.

What this file is for:
    It applies the rules of rules.yaml to the user's answers. It follows the order
    of the diagrams PDF, chapter 2:
        step 0  keep only the active answers; inactive and unknown answers are ignored
        step 1  input errors        R_SCOPE, R_REQUIRED, R_PRICE, R_PAY
        step 2  warnings            W_PRICE, W_CONSUMER
                -> if step 1 found an error, stop here (decision D17)
        step 3  select clauses      the SEL_ rules
        step 4  fill placeholders   placeholders.py; a gap that stays empty = R_REQUIRED
        step 5  final checks        R_CROSS (one clause per slot)
    It returns one dictionary, the "result":
        can_generate      True only if there is no error
        law_version       the legal basis used (sources.yaml)
        errors            R_ rules that fired (block "Generate")
        warnings          W_ rules that fired ("Generate" stays possible)
        selected_clauses  the review records: one per selected clause, with the filled text
        ignored_fields    answers that were ignored because they are inactive or unknown

How it fits into the project:
    app.py calls evaluate() every time the answers are checked; generator.py builds
    the Word file from the result; the tests compare the result with the expected one.
    The engine contains no legal wording (all wording is in the YAML files), no Word
    code and no Streamlit, so it can be tested with pytest alone (AI_PROMPT section 6).

Which documents it implements:
    - Diagrams PDF chapter 2 (order of the steps)
    - Handoff App. B: None = not answered, false = answered "no"; inactive inputs are ignored
    - Handoff App. C: rule types, "any error blocks Generate", review record of every clause
    - Decisions D6 (conditions), D16-D20, D24-D28 (result), D42 (cases with checks)

Example:
    from engine import evaluate
    result = evaluate(answers)                    # answers = {"price_type": "fixed", ...}
    result["can_generate"]                        # -> True or False
    result["selected_clauses"][0]["text"]         # -> "The fixed price for the Works is CHF ..."
"""

from checks import CHECKS, is_empty  # the special checks and the definition of "not answered"
from data_loader import load_knowledge  # reads and checks the YAML files
from placeholders import build_values, fill_text  # fills the gaps of a clause


ERROR_TYPES = ("error", "require")  # rule types that block "Generate" (handoff App. C)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def evaluate(answers, knowledge=None):
    """Apply all rules to the answers and return the result dictionary (see the top of this file).

    Parameters:
        answers: the user's answers {field_id: value}. Types (decision D25): Decimal
            for money and percentages, date for dates, True/False, text, and a list of
            dictionaries for tables such as milestones. Missing answers may be left out
            or set to None. Floats are refused, so money is never a float.
        knowledge: the result of data_loader.load_knowledge(). If None, the YAML files
            in data/ are loaded (the app loads them once and passes them in).
    Returns:
        The result dictionary.
    Raises:
        TypeError if an answer is a float; ValueError if rules.yaml names a check
        that does not exist in checks.py.
    """
    if knowledge is None:  # no knowledge base given
        knowledge = load_knowledge()  # read and check the YAML files in data/
    _verify_check_names(knowledge)  # every "check" named in rules.yaml must exist in checks.py

    # step 0: keep only the active answers (handoff App. B "Inactive inputs are ignored")
    active, ignored = _active_answers(answers, knowledge)  # active = {field_id: value}, ignored = [field_id, ...]

    # steps 1 and 2: input errors and warnings
    entries = _run_rules(1, active, knowledge, []) + _run_rules(2, active, knowledge, [])  # everything that fired
    errors = [entry for entry in entries if entry["type"] in ERROR_TYPES]  # R_ rules: block "Generate"
    warnings = [entry for entry in entries if entry["type"] == "warning"]  # W_ rules: only inform (D18)

    records = []  # the review records of the selected clauses
    if not errors:  # D17: clauses are only selected when the input is valid
        # step 3: select the clauses
        for position, (clause, rule) in enumerate(_select_clauses(active, knowledge), start=1):  # 1, 2, ...
            # step 4: fill the gaps of this clause
            values = build_values(clause, active, knowledge)  # {placeholder_name: text}
            text = fill_text(clause["text"], values)  # the clause text with the gaps filled
            for name in clause["inputs"]:  # each gap of the clause
                if name not in values:  # it could not be filled
                    errors.append(_unfilled_gap_error(name, knowledge))  # App. C: unresolved placeholder = R_REQUIRED
            records.append(_review_record(position, clause, rule, text, active, knowledge, warnings))  # the record
        # step 5: final checks on the selected clauses (R_CROSS)
        errors += _run_rules(5, active, knowledge, [record["clause_id"] for record in records])  # slot counting

    return {  # the result (decision D27)
        "can_generate": not errors,  # handoff App. C: any error blocks "Generate"
        "law_version": knowledge["law_version"],  # e.g. "2026-10-01"
        "errors": errors,  # list of error entries
        "warnings": warnings,  # list of warning entries
        "selected_clauses": records,  # list of review records, in contract order
        "ignored_fields": ignored,  # e.g. ["milestones"] when paying on delivery
    }  # end of the result


# ---------------------------------------------------------------------------
# Conditions (decision D6) - also used by app.py to show or hide questions
# ---------------------------------------------------------------------------

def condition_is_true(condition, answers):
    """Return True if a condition from the YAML files is true for these answers.

    Forms: {always: true}, {all: [...]}, {any: [...]}, {not: {...}},
    {field, op, value} and {field, op: is_empty / is_filled}.
    A missing answer makes an order comparison (less_than, at_most, ...) false, so
    only R_REQUIRED reports it; not_equals with a missing answer is true.

    Example: condition_is_true({"field": "contract_price", "op": "at_most", "value": Decimal("0")},
                               {"contract_price": Decimal("0")})  -> True
    """
    if "always" in condition:  # {always: true}
        return True  # always true
    if "all" in condition:  # AND: every part must be true
        return all(condition_is_true(part, answers) for part in condition["all"])  # check each part
    if "any" in condition:  # OR: at least one part must be true
        return any(condition_is_true(part, answers) for part in condition["any"])  # check each part
    if "not" in condition:  # NOT: the inner condition must be false
        return not condition_is_true(condition["not"], answers)  # turn the result around
    value = answers.get(condition["field"])  # the user's answer; None if not answered
    op = condition["op"]  # the operator, e.g. "equals"
    if op == "is_empty":  # no answer?
        return is_empty(value)  # True if not answered
    if op == "is_filled":  # an answer?
        return not is_empty(value)  # True if answered
    target = condition["value"]  # the value to compare with (already the right type, see data_loader.py)
    if op == "equals":  # same value
        return value == target  # e.g. price_type == "fixed"
    if op == "not_equals":  # different value (also True when unanswered)
        return value != target  # e.g. scope_confirmed != True
    if op == "one_of":  # the answer is one of a list
        return value in target  # e.g. price_type in ["fixed", "estimate"]
    if is_empty(value):  # the order comparisons below need an answer
        return False  # missing answer: false, so only R_REQUIRED reports it
    if op == "less_than":  # <
        return value < target  # e.g. contract_date < 2026-01-01
    if op == "at_most":  # <=
        return value <= target  # e.g. contract_price <= 0
    if op == "greater_than":  # >
        return value > target  # e.g. amount > 0
    if op == "at_least":  # >=
        return value >= target  # e.g. days >= 0
    raise ValueError(f"unknown operator '{op}'")  # cannot happen after data_loader.py; a safety net


def is_active(field_id, answers, knowledge):
    """Return True if a field is active (shown and used) for these answers.

    A field without "active_when" is always active (parameters.yaml).
    Example: is_active("estimate_basis", {"price_type": "fixed"}, knowledge) -> False
    """
    condition = knowledge["fields"][field_id].get("active_when")  # the field's condition, or None
    return condition is None or condition_is_true(condition, answers)  # active if no condition or condition true


# ---------------------------------------------------------------------------
# Step 0: active answers
# ---------------------------------------------------------------------------

def _active_answers(answers, knowledge):
    """Return (active, ignored).

    active:  {field_id: value} for every ACTIVE field in questionnaire order;
             an unanswered active field gets the value None. So "field_id in active"
             means "the field is active" (checks.py relies on this).
    ignored: the IDs of answers that are left out because their field is inactive or
             unknown (e.g. old milestones while paying on delivery, scenario E8 / P9).
    """
    active = {}  # the active answers, filled below
    for field_id in knowledge["fields"]:  # each field of parameters.yaml, in questionnaire order
        if is_active(field_id, answers, knowledge):  # shown and used for these answers
            value = answers.get(field_id)  # the answer, or None if not given
            _reject_floats(value, field_id)  # money must never be a float (D25)
            active[field_id] = value  # keep it
    ignored = [field_id for field_id, value in answers.items() if field_id not in active and not is_empty(value)]  # left out
    return active, ignored  # both lists


def _reject_floats(value, where):
    """Raise TypeError if value (or anything inside it) is a float (decision D25)."""
    if isinstance(value, float):  # e.g. 100000.0 instead of Decimal("100000")
        raise TypeError(f"answer '{where}' is a float; use Decimal for amounts and percentages (decision D25)")  # stop
    if isinstance(value, list):  # a table: check every row
        for item in value:  # each row
            _reject_floats(item, where)  # same check
    elif isinstance(value, dict):  # a row: check every cell
        for key, item in value.items():  # each cell
            _reject_floats(item, f"{where}.{key}")  # same check, e.g. "milestones.percent"


def _verify_check_names(knowledge):
    """Raise ValueError if rules.yaml names a check that checks.py does not have."""
    for rule in knowledge["rules"].values():  # each rule
        for case in rule.get("cases", []):  # each case (SEL_ rules have none)
            name = case.get("check")  # the named check, or None
            if name is not None and name not in CHECKS:  # named but not in checks.py
                raise ValueError(f"rules.yaml, {rule['id']}: check '{name}' does not exist in checks.py")  # stop


# ---------------------------------------------------------------------------
# Steps 1, 2 and 5: R_ and W_ rules
# ---------------------------------------------------------------------------

def _run_rules(step, active, knowledge, selected):
    """Run every R_ and W_ rule of one engine step and return the entries that fired.

    For each case whose "when" is true:
      - with a "check": one entry per place the check reports (e.g. per missing field)
      - without a check: one entry for the case's "field"
    selected = the clause IDs selected so far (only used by step 5).
    """
    entries = []  # what fired, in the order of rules.yaml
    for rule in knowledge["rules"].values():  # each rule, in file order
        if rule["step"] != step or rule["type"] == "select":  # another step, or a SEL_ rule
            continue  # skip it
        for case in rule["cases"]:  # each way the rule can fire
            if not condition_is_true(case["when"], active):  # the case does not apply
                continue  # go to the next case
            if "check" in case:  # a special check decides where the problem is
                places = CHECKS[case["check"]](active, knowledge, selected)  # e.g. ["client_name", "site_address"]
            else:  # no check: the case itself names the field
                places = [case.get("field")]  # one place (None = not tied to a question)
            message = case.get("message") or rule["message"]  # the case's own message, else the rule's (D42)
            for place in places:  # one entry per place
                entries.append(_entry(rule, place, message))  # remember what fired
    return entries  # may be empty


def _entry(rule, field, message):
    """Build one error or warning entry for the result."""
    return {  # the entry
        "rule_id": rule["id"],  # e.g. "R_PRICE"
        "type": rule["type"],  # error, require or warning
        "category": rule["category"],  # LAW or PRODUCT
        "topic": rule.get("topic"),  # e.g. "PRICE_PAYMENT", or None for the whole project
        "field": field,  # the question the message belongs to (a slot ID for R_CROSS, or None)
        "message": message,  # the text shown to the user
        "citations": list(rule["citations"]),  # legal basis (citation IDs)
        "rule_version": rule["version"],  # version of the rule (handoff App. E)
    }  # end of the entry


def _unfilled_gap_error(name, knowledge):
    """Return an R_REQUIRED error for a clause gap that could not be filled (handoff App. C)."""
    rule = knowledge["rules"]["R_REQUIRED"]  # the rule that reports missing input
    if name in knowledge["fields"]:  # the gap is a direct answer
        field = name  # show the error at that question
    else:  # the gap is a derived text
        field = knowledge["derived_placeholders"][name]["chosen_by"]  # show it at the answer that chooses the text
    return _entry(rule, field, rule["message"])  # an ordinary R_REQUIRED entry


# ---------------------------------------------------------------------------
# Step 3: select clauses
# ---------------------------------------------------------------------------

def _select_clauses(active, knowledge):
    """Return [(clause, SEL_ rule), ...] for every SEL_ rule whose condition is true.

    The list is sorted by the topic's order_in_contract (clauses.yaml, D31); clauses
    of the same topic keep the order of rules.yaml.
    """
    selections = []  # (clause, rule) pairs
    for rule in knowledge["rules"].values():  # each rule, in file order
        if rule["type"] == "select" and condition_is_true(rule["when"], active):  # a SEL_ rule that applies
            selections.append((knowledge["clauses"][rule["clause"]], rule))  # the clause it selects, and why

    def topic_position(selection):  # sort key: where the clause's topic comes
        clause = selection[0]  # the clause of the pair
        return knowledge["topics"][clause["topic"]]["order_in_contract"]  # e.g. 1 for PRICE_PAYMENT

    return sorted(selections, key=topic_position)  # stable sort: same topic keeps the file order


# ---------------------------------------------------------------------------
# Review records (handoff App. C "Review record required for every selected clause")
# ---------------------------------------------------------------------------

def _review_record(position, clause, rule, text, active, knowledge, warnings):
    """Build the review record of one selected clause.

    It stores everything the handoff asks for: clause_id, clause_version,
    selection_rule_id, actual input values, article/paragraph references, source,
    law_version and warnings, plus what the review screen and the generator need.
    """
    return {  # the review record
        "position": position,  # 1, 2, ... order in the result
        "clause_id": clause["id"],  # e.g. "PRICE_FIXED"
        "clause_version": clause["version"],  # e.g. "1.1"
        "topic_id": clause["topic"],  # e.g. "PRICE_PAYMENT"
        "title": clause["title"],  # review screen title, e.g. "Fixed price"
        "slot": clause["slot"],  # place in the Word template, e.g. "price_clause"
        "selection_rule_id": rule["id"],  # why it was selected, e.g. "SEL_PRICE_FIXED"
        "reason": rule["reason"],  # the plain-language reason (law packet Task 10)
        "input_values": _input_values(clause, active, knowledge),  # the answers the clause used
        "text": text,  # the clause text with all gaps filled
        "citations": [_citation_details(citation_id, knowledge) for citation_id in clause["citations"]],  # legal basis
        "basis_note": clause.get("basis_note"),  # App. D "Basis" line, review screen only
        "law_version": knowledge["law_version"],  # handoff App. C: stored in every record
        "warnings": _topic_warnings(warnings, clause["topic"]),  # IDs of the warnings of the same topic (D28)
    }  # end of the record


def _input_values(clause, active, knowledge):
    """Return the answers a clause used: its direct fields plus the fields its derived texts are built from.

    Example for PRICE_FIXED: {"contract_price": Decimal("100000"), "vat_treatment": "included"}
    """
    names = []  # field IDs, maybe with duplicates
    for name in clause["inputs"]:  # each gap of the clause
        if name in knowledge["fields"]:  # a direct answer
            names.append(name)  # use it
        else:  # a derived text
            names.extend(knowledge["derived_placeholders"][name]["built_from"])  # the answers it is built from
    return {name: active.get(name) for name in dict.fromkeys(names)}  # dict.fromkeys removes duplicates, keeps order


def _citation_details(citation_id, knowledge):
    """Return a citation with its source, ready for the review screen (never for the contract)."""
    citation = knowledge["citations"][citation_id]  # from sources.yaml
    source = knowledge["sources"][citation["source"]]  # the document it is in
    return {  # what the review screen shows
        "citation_id": citation_id,  # e.g. "CO_373_1_TO_3"
        "label": citation["label"],  # e.g. "Art. 373 para. 1-3 CO"
        "summary": citation.get("summary"),  # one sentence from note sheet 1
        "source_id": source["id"],  # e.g. "S1"
        "source_title": source["title"],  # e.g. "Swiss Code of Obligations SR 220"
        "url": source["url"],  # link to the official text
    }  # end of the citation


def _topic_warnings(warnings, topic_id):
    """Return the IDs of the warnings that belong to this topic, without duplicates (D28)."""
    ids = [warning["rule_id"] for warning in warnings if warning["topic"] == topic_id]  # e.g. ["W_PRICE", "W_PRICE"]
    return list(dict.fromkeys(ids))  # remove duplicates, keep order: ["W_PRICE"]
