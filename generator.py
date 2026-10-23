"""generator.py - builds the Word contract from the engine's result.

What this file is for:
    It fills the Word template (templates/contract_template.docx, built by
    templates/make_template.py) and returns the finished contract as bytes, ready
    for a download button. It fills three kinds of gaps:
      - clause slots, e.g. {{ price_clause }}: the filled clause text from the
        engine's review record with that "slot" (decision D30)
      - skeleton fields, e.g. {{ client_name }} or {{ contract_date }}: the user's
        answers, formatted like in the clauses (decision D35); an empty optional
        answer prints the field's "if_empty_print" text (parameters.yaml)
      - {{ annex_register }} and {{ has_annexes }}: the list of technical annexes
        and whether there is any (law colleague's answer 2)
    It refuses to generate (GenerationError) if the result has errors, if a clause
    gap is still open, or if a template gap has no value (AI_PROMPT step 15).

How it fits into the project:
    app.py calls generate_contract(result, answers, knowledge) when the user clicks
    the download button. There is no rule logic here: which clauses go into the
    contract was decided by engine.py; this file only puts the texts in place.
    No Streamlit, no legal sources in the contract (handoff App. C).

Which documents it implements:
    AI_PROMPT step 15 (fill the template, return bytes, refuse on errors or open
    placeholders), plan section 7.6, contract skeleton, decisions D30, D33, D35.

Example:
    from engine import evaluate
    from generator import generate_contract
    result = evaluate(answers, knowledge)
    word_bytes = generate_contract(result, answers, knowledge)
    open("contract.docx", "wb").write(word_bytes)
"""

from io import BytesIO  # a file in memory: the contract is returned as bytes, not saved to disk
from pathlib import Path  # path of the template file

from docxtpl import DocxTemplate  # fills the {{ gaps }} of a Word template
from jinja2 import Environment, StrictUndefined  # StrictUndefined: a gap without a value is an error, not empty

from checks import is_empty  # the definition of "not answered"
from data_loader import load_knowledge  # the knowledge base, if none is passed in
from placeholders import format_date, format_value  # the same formats as in the clauses (D35)


TEMPLATE_PATH = Path(__file__).parent / "templates" / "contract_template.docx"  # the default template
ANNEX_FIELD = "annex_register"  # the field with the list of technical annexes
HAS_ANNEXES = "has_annexes"  # the true/false gap that chooses the paragraph versions in sections 2, 3 and 13
ANNEX_LINE = "{index}. {title} | {date} | Revision {revision}"  # one line per annex (format proposed, not legal wording)


class GenerationError(Exception):
    """Raised when the contract must not or cannot be generated; the message says why."""


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def generate_contract(result, answers, knowledge=None, template_path=TEMPLATE_PATH):
    """Fill the Word template and return the finished contract as bytes.

    Parameters:
        result: the result of engine.evaluate() for these answers
        answers: the user's answers (for the skeleton fields: names, addresses, date, ...)
        knowledge: the result of data_loader.load_knowledge(); loaded from data/ if None
        template_path: the Word template; the default is templates/contract_template.docx
    Returns:
        The Word file (.docx) as bytes.
    Raises:
        GenerationError if the result has errors, a clause gap is still open, or a
        gap of the template has no value.
    """
    if knowledge is None:  # no knowledge base given
        knowledge = load_knowledge()  # read the YAML files in data/
    if not result["can_generate"] or result["errors"]:  # handoff App. C: any error blocks "Generate"
        rule_ids = ", ".join(sorted({error["rule_id"] for error in result["errors"]}))  # e.g. "R_PAY, R_PRICE"
        raise GenerationError(f"The contract cannot be generated while there are errors: {rule_ids}")  # stop
    _check_clause_gaps_are_filled(result, knowledge)  # no "{contract_price}" may be left in a clause text

    document = DocxTemplate(template_path)  # open the template
    gaps = document.get_undeclared_template_variables()  # the names of all {{ gaps }} in the template
    context = _build_context(gaps, result, answers, knowledge)  # a value for every gap
    environment = Environment(undefined=StrictUndefined)  # safety net: an unknown gap stops the rendering
    document.render(context, jinja_env=environment, autoescape=True)  # fill the gaps; autoescape keeps "&" and "<" safe
    buffer = BytesIO()  # an empty file in memory
    document.save(buffer)  # write the finished contract into it
    return buffer.getvalue()  # the Word file as bytes


# ---------------------------------------------------------------------------
# Safety check on the clause texts
# ---------------------------------------------------------------------------

def _check_clause_gaps_are_filled(result, knowledge):
    """Raise GenerationError if a selected clause text still contains one of its own {placeholders}.

    Only the clause's own placeholder names are searched, so braces typed by a user
    (e.g. "rate {see annex}") do not block the contract.
    """
    open_gaps = []  # e.g. ["PRICE_FIXED: {contract_price}"]
    for record in result["selected_clauses"]:  # each selected clause
        clause = knowledge["clauses"][record["clause_id"]]  # its definition in clauses.yaml
        for name in clause["inputs"]:  # each placeholder the clause declares
            if "{" + name + "}" in record["text"]:  # still in the text: not filled
                open_gaps.append(f"{record['clause_id']}: {{{name}}}")  # remember it
    if open_gaps:  # at least one gap is open
        raise GenerationError("Clause placeholders are not filled: " + ", ".join(open_gaps))  # stop


# ---------------------------------------------------------------------------
# Values for the gaps of the template
# ---------------------------------------------------------------------------

def _build_context(gaps, result, answers, knowledge):
    """Return {gap_name: value} for every gap of the template.

    Raises GenerationError with the list of gaps that have no value.
    """
    slot_texts = {record["slot"]: record["text"] for record in result["selected_clauses"]}  # slot -> filled clause
    context = {}  # the values, filled below
    problems = []  # gaps without a value
    for gap in sorted(gaps):  # each gap, in alphabetical order (only matters for the error message)
        if gap in knowledge["slots"]:  # a clause slot, e.g. price_clause
            if gap in slot_texts:  # a clause was selected for it
                context[gap] = slot_texts[gap]  # the filled clause text
            else:  # no clause for this slot
                problems.append(f"no clause selected for {{{{ {gap} }}}}")  # remember it
        elif gap == HAS_ANNEXES:  # chooses the paragraph versions in sections 2, 3 and 13
            context[gap] = not is_empty(answers.get(ANNEX_FIELD))  # True if at least one annex is listed
        elif gap == ANNEX_FIELD:  # the annex list of section 3
            context[gap] = _annex_lines(answers.get(ANNEX_FIELD))  # one line per annex
        elif gap in knowledge["fields"]:  # a skeleton field, e.g. client_name
            text = _field_text(knowledge["fields"][gap], answers.get(gap))  # formatted answer, or the empty text
            if text is None:  # no answer and no text for an empty answer
                problems.append(f"no value for {{{{ {gap} }}}}")  # remember it
            else:  # a value exists
                context[gap] = text  # use it
        else:  # a gap the generator does not know
            problems.append(f"the template gap {{{{ {gap} }}}} is not a slot or a field")  # remember it
    if problems:  # at least one gap has no value
        raise GenerationError("The template cannot be filled: " + "; ".join(problems))  # stop
    return context  # every gap has a value


def _field_text(field, value):
    """Return the text for one skeleton field, or None if it has no value and no empty text.

    An empty optional answer prints the field's "if_empty_print" text (law packet Task 5),
    e.g. "No separate list of exclusions or Client-supplied items is recorded in this document."
    """
    if is_empty(value):  # not answered
        return field.get("if_empty_print")  # the text for an empty answer, or None
    return format_value(field, value)  # e.g. a date becomes "1 November 2026"


def _annex_lines(rows):
    """Return the annex list of section 3, one line per annex, or "" if there is none.

    Example line: "1. Bathroom technical specification | 1 November 2026 | Revision A"
    """
    if is_empty(rows):  # no annexes: section 3 shows the "no annexes" version instead
        return ""  # the gap still needs a value
    lines = []  # the finished lines
    for index, row in enumerate(rows, start=1):  # each annex, numbered from 1
        lines.append(ANNEX_LINE.format(index=index, title=row["title"],  # number and title
                                       date=format_date(row["date"]), revision=row["revision"]))  # date and revision
    return "\n".join(lines)  # one annex per line (docxtpl turns "\n" into a line break)
