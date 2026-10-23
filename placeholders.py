"""placeholders.py - turns answers into the texts that fill the {placeholders} of a clause.

What this file is for:
    Clause texts contain gaps such as {contract_price} or {milestones_schedule}.
    This module produces the text for each gap:
    - formatting of answers: CHF amounts, percentages and dates (decision D35)
    - derived texts built from answers with fixed wording from clauses.yaml:
      vat_treatment_text, milestone_reconciliation_text and milestones_schedule
    - the CHF amount of each milestone with the rounding rule (decision D23)
    - filling a text: replacing every {name} by its value

How it fits into the project:
    engine.py (engine step 4 "fill placeholders") calls build_values() and fill_text().
    checks.py uses milestone_amounts() to check that every instalment is positive (R_PAY).
    generator.py uses format_chf() and format_date() for the fields of the Word template.
    This module never decides WHETHER a clause is used (that is the rules' job),
    contains no legal wording of its own (all wording is in clauses.yaml) and does
    not import Streamlit.

Which documents it implements:
    - Legal handoff App. D "Deterministic text assembly"
    - Legal handoff App. B "Milestone records": round all but the last instalment to
      cents, the last one takes the balance; decision D23: half-up, also for estimates
    - Law packet page 7: milestone row wording and advance labels
    - Decisions D10 (derived placeholders), D35 (formats), D36 (one line per milestone)
"""

from decimal import Decimal, ROUND_HALF_UP  # exact money maths; ROUND_HALF_UP = normal rounding (0.005 -> 0.01)

from data_loader import PLACEHOLDER_PATTERN  # the pattern that finds {name}; defined once, in data_loader.py


CENT = Decimal("0.01")  # the smallest money unit we keep: one cent (Rappen)
HUNDRED = Decimal("100")  # turns a percentage into a share: 20 % of a price = price * 20 / 100

# month names for dates like "31 December 2027" (D35); written out here so the
# result does not depend on the language settings of the computer
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",  # months 1-6
    "July", "August", "September", "October", "November", "December",  # months 7-12
)  # end of the month names


# ---------------------------------------------------------------------------
# Formatting single values (decision D35)
# ---------------------------------------------------------------------------

def format_chf(amount):
    """Format a CHF amount with thousands separators and exactly 2 decimals.

    "CHF" itself is already written in the clause texts, so it is not added here.
    Example: format_chf(Decimal("100000")) -> "100,000.00"
    """
    rounded = amount.quantize(CENT, rounding=ROUND_HALF_UP)  # round to cents (half-up), e.g. 10.005 -> 10.01
    return f"{rounded:,.2f}"  # "," = thousands separator, ".2f" = always 2 decimals


def format_percent(value):
    """Format a percentage without unnecessary zeros.

    Examples: Decimal("20") -> "20", Decimal("20.00") -> "20", Decimal("33.33") -> "33.33"
    """
    return f"{value.normalize():f}"  # normalize() drops trailing zeros; ":f" avoids the form "2E+1"


def format_date(day):
    """Format a date as day, month name and year.

    Example: format_date(date(2027, 12, 31)) -> "31 December 2027"
    """
    return f"{day.day} {MONTH_NAMES[day.month - 1]} {day.year}"  # month 1 is at position 0 of MONTH_NAMES


def format_value(field, value):
    """Turn one answer into the text printed in the contract, depending on the field's type.

    Parameters:
        field: the field's definition from parameters.yaml (needs "id" and "type")
        value: the answer, e.g. Decimal("100000") or date(2027, 12, 31)
    Examples: decimal_chf 100000 -> "100,000.00"; date -> "31 December 2027"; text stays text.
    """
    field_type = field["type"]  # the data type from parameters.yaml
    if field_type == "decimal_chf":  # money
        return format_chf(value)  # e.g. "100,000.00"
    if field_type == "decimal_percent":  # percentage
        return format_percent(value)  # e.g. "33.33"
    if field_type == "date":  # calendar date
        return format_date(value)  # e.g. "31 December 2027"
    if field_type == "list":  # a table cannot go into a sentence as it is
        raise ValueError(f"field {field['id']} is a list; it needs its own builder")  # programming mistake
    return str(value)  # text, long_text, integer, enum and boolean are printed as they are


# ---------------------------------------------------------------------------
# Milestone amounts (handoff App. B, decision D23)
# ---------------------------------------------------------------------------

def milestone_amounts(price, percents):
    """Split a price into instalments, one per percentage.

    Every instalment except the last is rounded half-up to cents; the last one
    takes the balance, so all instalments always add up exactly to the price.
    The same rule is used for fixed prices and for estimates (decision D23).
    The percentages should add up to 100; rule R_PAY checks that.

    Example: milestone_amounts(Decimal("99999.99"), [Decimal("50"), Decimal("50")])
             -> [Decimal("50000.00"), Decimal("49999.99")]
    """
    amounts = []  # the instalments, filled below
    for percent in percents[:-1]:  # every percentage except the last one
        share = price * percent / HUNDRED  # the exact share, e.g. 99999.99 * 50 / 100 = 49999.995
        amounts.append(share.quantize(CENT, rounding=ROUND_HALF_UP))  # rounded to cents: 50000.00
    if percents:  # at least one milestone exists
        amounts.append(price - sum(amounts, Decimal("0")))  # the last instalment = what is left of the price
    return amounts  # one amount per percentage, in the same order


# ---------------------------------------------------------------------------
# Derived placeholders (decision D10)
# ---------------------------------------------------------------------------

def build_derived(placeholder, answers):
    """Build the text of one derived placeholder from the answers.

    Parameters:
        placeholder: its definition from clauses.yaml, section "derived_placeholders"
        answers: the user's answers {field_id: value}
    Returns:
        The text, or None if an answer it needs is missing. The placeholder then
        stays unfilled and the engine reports it under R_REQUIRED.
    Raises:
        ValueError if clauses.yaml declares a derived placeholder that this module
        cannot build (a new one needs a builder below).

    Example: for vat_treatment_text and the answer vat_treatment = "included"
             -> "This amount includes applicable VAT."
    """
    if "text_by_answer" in placeholder:  # the simple kind: one fixed text per answer
        answer = answers.get(placeholder["chosen_by"])  # e.g. the answer of vat_treatment: "included"
        return placeholder["text_by_answer"].get(answer)  # the matching text, or None if unanswered
    builder = SPECIAL_BUILDERS.get(placeholder["id"])  # placeholders that need their own function (list below)
    if builder is None:  # declared in clauses.yaml, but nothing here can build it
        raise ValueError(f"no builder for derived placeholder '{placeholder['id']}' in placeholders.py")  # tell the team
    return builder(placeholder, answers)  # build it, e.g. the milestone schedule


def _build_milestones_schedule(placeholder, answers):
    """Build {milestones_schedule}: one numbered line per milestone (App. D, law packet page 7, D36).

    The rows are expected to be complete (rule R_PAY blocks incomplete rows before
    the engine fills placeholders).

    Example line for a fixed price:
        "1. Deposit | Trigger: Contract signed | Share of fixed price: 20% | Instalment:
         CHF 20,000.00 | Invoice period: 10 calendar days after receipt |
         Pre-performance advance: payable before the corresponding work is performed."
    """
    milestones = answers.get("milestones")  # the rows typed by the user
    price = answers.get("contract_price")  # the price the rows share
    row_template = placeholder["row_by_answer"].get(answers.get(placeholder["chosen_by"]))  # fixed or estimate wording
    if not milestones or price is None or row_template is None:  # something needed is missing
        return None  # leave the placeholder unfilled; the engine reports it
    amounts = milestone_amounts(price, [row["percent"] for row in milestones])  # CHF amount of each row (D23)
    lines = []  # the finished lines, filled below
    for index, (row, amount) in enumerate(zip(milestones, amounts), start=1):  # each row with its amount, numbered from 1
        label_key = "advance_label_if_true" if row["advance"] is True else "advance_label_if_false"  # which advance label
        row_values = {  # the values for the {names} in the row template
            "index": str(index),  # 1, 2, 3 ...
            "name": row["name"],  # e.g. "Deposit"
            "trigger": row["trigger"],  # e.g. "Contract signed"
            "percent": format_percent(row["percent"]),  # e.g. "20"
            "amount_chf": format_chf(amount),  # e.g. "20,000.00"
            "invoice_due_days": str(row["invoice_due_days"]),  # e.g. "10"
            "advance_label": placeholder[label_key],  # the fixed advance sentence from clauses.yaml
        }  # end of the row values
        lines.append(fill_text(row_template, row_values))  # the finished line
    return "\n" + "\n".join(lines) + "\n"  # every milestone on its own line (D36)


# derived placeholders that need their own function; the simple "text_by_answer"
# kind needs no entry here, it is handled by build_derived() directly
SPECIAL_BUILDERS = {
    "milestones_schedule": _build_milestones_schedule,  # numbered milestone lines with amounts
}  # end of the special builders


# ---------------------------------------------------------------------------
# Values for a whole clause, and filling a text
# ---------------------------------------------------------------------------

def build_values(clause, answers, knowledge):
    """Return the text for every placeholder of one clause, as {placeholder_name: text}.

    Placeholders whose answer is missing are left out, so fill_text() leaves them
    in the text and the engine can report them under R_REQUIRED.

    Parameters:
        clause: the clause from clauses.yaml (its "inputs" lists the placeholders)
        answers: the user's answers {field_id: value}
        knowledge: the result of data_loader.load_knowledge()
    Example for PRICE_FIXED with price 100000 and VAT included:
        {"contract_price": "100,000.00", "vat_treatment_text": "This amount includes applicable VAT."}
    """
    values = {}  # the result, filled below
    for name in clause["inputs"]:  # each placeholder the clause declares
        if name in knowledge["fields"]:  # a direct answer, e.g. contract_price
            answer = answers.get(name)  # the user's answer; None if missing
            if answer is not None and answer != "":  # only answered fields are filled
                values[name] = format_value(knowledge["fields"][name], answer)  # the formatted text
        else:  # a derived placeholder (the data loader made sure there is no third kind)
            text = build_derived(knowledge["derived_placeholders"][name], answers)  # the built text, or None
            if text is not None:  # it could be built
                values[name] = text  # use it
    return values  # {placeholder_name: text}


def fill_text(text, values):
    """Replace every {name} in text by values[name]; a name without a value stays as it is.

    Spaces next to line breaks are removed, so the lines of a schedule do not
    start or end with a space.

    Example: fill_text("CHF {contract_price}.", {"contract_price": "100,000.00"}) -> "CHF 100,000.00."
    """
    def replacement(match):  # called once for every {name} found in the text
        name = match.group(1)  # the name between the braces, e.g. "contract_price"
        return values.get(name, match.group(0))  # its value, or the unchanged "{name}" if there is none

    filled = PLACEHOLDER_PATTERN.sub(replacement, text)  # replace every {name} in the text
    return filled.replace(" \n", "\n").replace("\n ", "\n")  # tidy the spaces around line breaks
