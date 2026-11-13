"""ui/questions.py - the questions of one step, the tables, and the messages below the questions.

What this file is for:
    It draws the active questions of the step shown (parameters.yaml, "active_when" via
    engine.is_active) with the right input element for each type, reads every answer in the
    type the engine expects (money and percentages as Decimal, D25; nothing preselected,
    handoff App. B), handles the editable tables (milestones, technical annexes) and shows
    the errors and warnings directly below their questions.
"""

from datetime import date, datetime  # date answers; datetime to recognise date-times from the table
from decimal import Decimal  # money and percentages become exact Decimal values (D25)

import streamlit as st  # the web user interface

from engine import is_active  # "is this question shown for these answers?"
from ui.citations import message_with_basis  # message + legal basis as Markdown
from ui.common import DECIMAL_TYPES, TABLE_YES_NO, YES_NO  # answer types and yes / no texts


def ask_questions(knowledge, section_id):
    """Draw the active questions of one section and return (answers, message_areas).

    answers:       {field_id: answer} of ALL active questions, also of the steps not shown
                   (the engine always checks everything)
    message_areas: {field_id: place directly below the question} for the questions drawn
    A question is only active when its "active_when" holds (parameters.yaml), e.g.
    estimate_basis only for an estimate. Fields are read in the order of parameters.yaml,
    so the answer a condition depends on (price_type) is known before the dependent question.
    On the last step (section_id None), no question is drawn; only the answers are read.
    """
    answers = {}  # the answers, filled below
    message_areas = {}  # the places for the messages, filled below
    for field_id, field in knowledge["fields"].items():  # each field, in file order
        if not is_active(field_id, answers, knowledge):  # not needed for these answers
            continue  # neither drawn nor given to the engine
        if field["section"] == section_id:  # a question of the step shown
            with st.container(border=True):  # each question in its own card
                ask(field, answers)  # draw the input element
                message_areas[field_id] = st.container()  # an empty place right below the question
        answers[field_id] = stored_answer(field)  # the current answer (drawn now or kept from another step)
    return answers, message_areas  # everything the rest of the page needs


def ask(field, answers):
    """Draw one question with the right input element for its type (the answer is read by stored_answer).

    Nothing is preselected: an unanswered question has the answer None (handoff App. B).
    The question and its help text are drawn above the input element (show_question);
    the input element's own label is therefore hidden ("collapsed").
    """
    label = question_text(field, answers)  # the question, maybe depending on another answer
    show_question(label, field.get("help_text"))  # bold question with its help text below it
    hide = "collapsed"  # hide the input element's own label (the question is already shown above it)
    key = field["id"]  # Streamlit remembers the answer under this key between clicks
    field_type = field["type"]  # the data type from parameters.yaml
    if field_type == "date":  # a calendar date
        st.date_input(label, value=None, format="DD.MM.YYYY", label_visibility=hide, key=key)  # None until chosen
    elif field_type == "enum":  # one answer from a list
        labels = {option["value"]: option["label"] for option in field["allowed_values"]}  # stored value -> text
        st.radio(label, list(labels), index=None, format_func=labels.get, label_visibility=hide, key=key)  # None until chosen
    elif field_type == "enum_list":  # any number of answers from a list
        labels = {option["value"]: option["label"] for option in field["allowed_values"]}  # stored value -> text
        st.multiselect(label, list(labels), format_func=labels.get, label_visibility=hide, key=key)  # [] until chosen
    elif field_type == "boolean":  # yes / no
        st.radio(label, [True, False], index=None, format_func=YES_NO.get, horizontal=True,
                 label_visibility=hide, key=key)  # None until chosen; False = answered "no"
    elif field_type == "text":  # one line of text
        st.text_input(label, label_visibility=hide, key=key)  # "" until typed
    elif field_type == "long_text":  # several lines of text
        st.text_area(label, label_visibility=hide, key=key)  # "" until typed
    elif field_type in DECIMAL_TYPES:  # money, or a percentage such as the maximum of a delay penalty
        st.number_input(label, value=None, step=0.01, format="%.2f", label_visibility=hide, key=key)  # a float or None
    elif field_type == "integer":  # whole number
        st.number_input(label, value=None, step=1, label_visibility=hide, key=key)  # an int or None
    elif field_type == "list":  # a table such as milestones or annexes
        ask_table(field, key)  # see below
    else:  # a type this file does not know
        raise ValueError(f"no input element for field type '{field_type}'")  # a new type needs a new element here


def show_question(label, help_text):
    """Show a question in bold with its help text directly below it, always visible.

    The help text is not hidden behind a small "?" pop-up: such a pop-up stayed open or
    came back after a click elsewhere. The steps are short, so the help text can be shown at once.
    """
    with st.container(gap=None):  # no space between the question and its help text
        st.markdown(f"**{label}**")  # the question in bold
        if help_text:  # the question has a help text (parameters.yaml "help_text")
            st.caption(help_text)  # small grey text below the question


def stored_answer(field):
    """Return the answer of one question in the type the engine expects (None if not answered).

    Money and percentages become exact Decimal values (D25); a table returns its cleaned rows.
    """
    key = field["id"]  # the key the answer is stored under
    if field["type"] == "list":  # a table: its rows are stored by ask_table
        return st.session_state["tables"].get(key, [])  # [] if the table was never filled
    value = st.session_state.get(key)  # the value of the input element (None if never shown)
    if field["type"] in DECIMAL_TYPES and value is not None:  # money or a percentage
        return Decimal(str(value))  # turn the float into an exact Decimal (D25)
    return value  # date, text, number, True / False, chosen value(s)


def question_text(field, answers):
    """Return the question text; some questions change with another answer (parameters.yaml "question_variants").

    Example: contract_price asks "What is the fixed total?" once price_type = fixed.
    """
    depends_on = field.get("question_depends_on")  # e.g. "price_type", or None
    if depends_on is None:  # the question never changes
        return field["question"]  # the normal question
    variant = field["question_variants"].get(answers.get(depends_on))  # the variant for the current answer
    return variant or field["question"]  # the normal question while the other answer is still missing


def ask_table(field, key):
    """Draw an editable table (rows can be added with "+") and store its cleaned rows in st.session_state["tables"].

    The question above the table is drawn by ask(). The table is drawn from its stored rows
    (or one empty row), so the rows survive a change of step. These starting rows stay the
    same during one visit of the step (table_base), because Streamlit applies the user's
    edits to the rows the table was first drawn with.
    """
    columns = field["columns"]  # the column definitions from parameters.yaml
    config = {column["id"]: table_column(column) for column in columns}  # how each column is edited
    base = st.session_state["table_base"]  # starting rows of the tables during this visit
    if key not in base:  # first drawing during this visit of the step
        base[key] = editor_rows(st.session_state["tables"].get(key, []), columns)  # from the stored rows
    rows = st.data_editor(base[key], column_config=config, num_rows="dynamic", hide_index=True,  # the table
                          key=f"{key}_table_{st.session_state['table_round']}")  # a new key for every visit
    st.session_state["tables"][key] = clean_rows(rows, columns)  # the rows in the types the engine expects


def editor_rows(rows, columns):
    """Turn stored table rows back into what the table shows; one empty row (with defaults) if there are none.

    Example: {"percent": Decimal("20"), "advance": True, ...} -> {"percent": 20.0, "advance": "Yes", ...}
    """
    if not rows:  # nothing stored yet
        return [{column["id"]: column.get("default") for column in columns}]  # one empty row
    return [{column["id"]: editor_cell(row.get(column["id"]), column) for column in columns} for row in rows]


def editor_cell(value, column):
    """Turn one stored cell back into what the table shows (the opposite of clean_cell)."""
    if column["type"] == "boolean":  # True / False
        return YES_NO.get(value)  # "Yes" / "No" (None stays empty)
    if isinstance(value, Decimal):  # a percentage or a number with decimals
        return float(value)  # the table works with normal numbers
    return value  # text, whole number, date or None


def table_column(column):
    """Return the Streamlit column setting for one column of a table, depending on its type."""
    label = column["question"]  # column heading, e.g. "Percent"
    help_text = column.get("help_text")  # shown when hovering over the heading
    column_type = column["type"]  # the data type from parameters.yaml
    if column_type == "decimal_percent":  # a percentage
        return st.column_config.NumberColumn(label, help=help_text, min_value=0, max_value=100, step=0.01, format="%.2f")
    if column_type == "integer":  # a whole number, e.g. invoice due days
        return st.column_config.NumberColumn(label, help=help_text, min_value=0, step=1)  # no negative numbers
    if column_type == "date":  # a date, e.g. of an annex
        return st.column_config.DateColumn(label, help=help_text, format="DD.MM.YYYY")  # day.month.year
    if column_type == "boolean":  # yes / no; a choice so that "not answered" stays possible
        return st.column_config.SelectboxColumn(label, help=help_text, options=list(TABLE_YES_NO))  # "Yes" / "No"
    return st.column_config.TextColumn(label, help=help_text, default=column.get("default"))  # text


def clean_rows(rows, columns):
    """Turn the table rows into the types the engine expects and leave out empty rows.

    Example: {"percent": 20.0, "invoice_due_days": 30.0, "advance": "Yes", ...}
          -> {"percent": Decimal("20.0"), "invoice_due_days": 30, "advance": True, ...}
    """
    cleaned = []  # the finished rows
    for row in rows:  # each row of the table
        values = {column["id"]: clean_cell(row.get(column["id"]), column) for column in columns}  # converted cells
        typed = [values[c["id"]] for c in columns if values[c["id"]] not in (None, c.get("default"))]  # cells the user filled
        if typed:  # the user filled at least one cell
            cleaned.append(values)  # keep the row (incomplete rows are reported by the engine)
    return cleaned  # [] if the table is empty


def clean_cell(value, column):
    """Turn one table cell into the type the engine expects (None for an empty cell)."""
    if value is None or value != value:  # empty cell (an empty number is "NaN", which is not equal to itself)
        return None  # not answered
    column_type = column["type"]  # the column's data type
    if column_type == "boolean":  # the "Yes" / "No" choice
        return TABLE_YES_NO.get(value)  # True / False
    if column_type == "decimal_percent":  # a percentage
        return Decimal(str(value))  # exact Decimal, never float (D25)
    if column_type == "integer":  # a whole number
        return int(value) if float(value).is_integer() else Decimal(str(value))  # 30.0 -> 30; 1.5 stays (R_PAY reports it)
    if column_type == "date":  # a date
        if isinstance(value, datetime):  # a date with a time of day
            return value.date()  # keep only the date
        return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])  # "2026-11-01" -> date
    return str(value)  # text


def show_messages(errors, warnings, message_areas, knowledge):
    """Show the errors (red) and warnings (yellow) of the questions drawn, right below each question.

    errors are the visible errors (see visible_errors); warnings are always shown at once.
    Messages of other steps, and messages without a question (e.g. W_CONSUMER, or R_CROSS
    which names a slot), are shown on the step "Check and review".
    """
    for error in errors:  # each visible error
        if error["field"] in message_areas:  # its question is on this step
            message_areas[error["field"]].error(message_with_basis(error, knowledge))  # red box: message + legal basis
    for warning in warnings:  # each warning (also shown when there are errors, D18)
        if warning["field"] in message_areas:  # its question is on this step
            message_areas[warning["field"]].warning(message_with_basis(warning, knowledge))  # yellow box
