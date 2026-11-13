"""ui/common.py - constants and small helpers used by several parts of the user interface.

What this file is for:
    The texts, value maps and helpers that more than one module of the ui package needs, so
    they are defined once: the prototype note, the yes / no texts, the answer types, the
    title of the last step, step_title() and section_of().
"""


# law packet Task 13: the prototype note (same text as below the contract title)
PROTOTYPE_NOTE = ("Academic prototype for seminar demonstration. This document may contain incomplete sections "
                  "and requires completion and legal review before use.")
YES_NO = {True: "Yes", False: "No"}  # how true / false answers are shown (questions and table cells)
TABLE_YES_NO = {"Yes": True, "No": False}  # the yes/no choice inside a table, turned back into true / false
REVIEW_TITLE = "Check and review"  # title of the last step (it has no section in parameters.yaml)
DECIMAL_TYPES = ("decimal_chf", "decimal_percent")  # answers that become exact Decimal values (D25)
EMPTY_ANSWERS = {"text": "", "long_text": "", "enum_list": []}  # "not answered" per type; every other type: None


def step_title(section_id, knowledge):
    """Return the title of a step, e.g. "Price and payment"; the last step is "Check and review"."""
    if section_id is None:  # the last step
        return REVIEW_TITLE  # it has no section in parameters.yaml
    return knowledge["sections"][section_id]["title"]  # the section title from parameters.yaml


def section_of(entry, knowledge):
    """Return the section of the question an error or warning belongs to (None if it has no question)."""
    field = knowledge["fields"].get(entry["field"])  # the question (None for e.g. W_CONSUMER or R_CROSS)
    return None if field is None else field["section"]  # e.g. "price_payment"
