"""app.py - the Streamlit user interface of the Construction Contract Generator.

What this file is for:
    It shows the questionnaire, checks the answers with the engine, shows errors
    (red) and warnings (yellow) next to the questions, shows the review screen
    (each clause with its reason and legal basis) and offers the Word contract
    for download. The flow follows the process flowchart (diagrams PDF ch. 1):
        questionnaire -> "Check answers" -> errors back to the questionnaire
                                         -> no errors: review screen -> download

How it fits into the project:
    Start it from the project root with:   streamlit run app.py
    This file only shows and collects; it contains no rule logic (AI_PROMPT section 6):
      - the questions come from data/parameters.yaml (via data_loader.py)
      - which questions are shown comes from "active_when" (engine.is_active)
      - all checks, clause choices and texts come from engine.evaluate()
      - the Word file comes from generator.generate_contract()
    The YAML files are loaded once; restart the app after changing a YAML file.
    The sidebar links to every section; the colours are set in .streamlit/config.toml.

Which documents it implements:
    AI_PROMPT step 17 (questionnaire with only active fields, milestones as a table,
    red errors next to the fields, yellow warnings, review screen, "Generate" disabled
    while errors exist, download button), diagrams PDF ch. 1 (user flow), handoff
    App. B (None = not answered: no answer is preselected), App. C (sources only on
    the review screen), law packet Task 13 (prototype note), decisions D18, D25, D28.
"""

from datetime import date, datetime  # date answers; datetime to recognise date-times from the table
from decimal import Decimal  # money and percentages become exact Decimal values (D25)
import html  # html.escape: section titles are written safely into the sidebar's HTML

import streamlit as st  # the web user interface

from data_loader import load_knowledge  # reads and checks the YAML files
from engine import evaluate, is_active  # the rule engine and "is this question shown?"
from generator import GenerationError, generate_contract  # builds the Word file


# law packet Task 13: the prototype note (same text as below the contract title)
PROTOTYPE_NOTE = ("Academic prototype for seminar demonstration. This document may contain incomplete sections "
                  "and requires completion and legal review before use.")
YES_NO = {True: "Yes", False: "No"}  # how true / false answers are shown
TABLE_YES_NO = {"Yes": True, "No": False}  # the yes/no choice inside a table, turned back into true / false
WORD_FILE_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # file type of .docx

# look of the sidebar menu: every section is a white card; colours match .streamlit/config.toml
SIDEBAR_STYLE = """
<style>
.nav-item {                                  /* one card in the sidebar menu */
  display: flex;                             /* title on the left, badge on the right */
  justify-content: space-between;            /* push the badge to the right edge */
  align-items: center;                       /* title and badge on the same height */
  padding: 0.65rem 0.9rem;                   /* space inside the card */
  margin-bottom: 0.5rem;                     /* space between the cards */
  background: #FFFFFF;                       /* white card on the beige sidebar */
  border: 1px solid #D6CCB8;                 /* thin beige border */
  border-radius: 0.6rem;                     /* rounded corners */
  color: #1A1A1A !important;                 /* dark text instead of a blue link */
  text-decoration: none !important;          /* no underline */
  font-weight: 500;                          /* slightly bold */
  transition: background 0.15s, color 0.15s; /* smooth colour change on hover */
}
.nav-item:hover {                            /* mouse over a card */
  background: #1F4E79;                       /* dark blue (primary colour) */
  border-color: #1F4E79;                     /* same colour for the border */
  color: #FFFFFF !important;                 /* white text */
}
.nav-badge {                                 /* red number of problems in a section */
  background: #B42318;                       /* red */
  color: #FFFFFF;                            /* white number */
  border-radius: 999px;                      /* pill shape */
  padding: 0.05rem 0.55rem;                  /* space around the number */
  font-size: 0.8rem;                         /* a bit smaller than the title */
}
.nav-ok {                                    /* green tick for a section without problems */
  color: #2E7D32;                            /* green */
  font-weight: 700;                          /* bold */
}
</style>
"""


@st.cache_resource  # load the YAML files only once, not on every click
def get_knowledge():
    """Return the knowledge base (all four YAML files, checked by data_loader.py)."""
    return load_knowledge()  # stops with a clear message if a YAML file has a mistake


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main():
    """Draw the whole page: questionnaire, check button, messages, review screen and download."""
    st.set_page_config(page_title="Construction Contract Generator")  # browser tab title
    knowledge = get_knowledge()  # the knowledge base
    st.title("Construction Contract Generator")  # page title
    st.caption(PROTOTYPE_NOTE)  # prototype note (law packet Task 13)
    general_messages = st.container()  # place for messages not tied to one question (e.g. W_CONSUMER)

    answers, message_areas = ask_questions(knowledge)  # the questionnaire; returns the answers

    st.divider()  # a line between the questionnaire and the check
    st.header("Check and review", anchor="check")  # target of the sidebar link "Check and review"
    if not st.session_state.get("checked"):  # not checked yet: show the button (only needed once)
        if st.button("Check answers", type="primary"):  # the user asks for the first check
            st.session_state["checked"] = True  # from now on, check after every change
            st.rerun()  # draw the page again at once, now with the messages and without the button
    else:  # already checked once: the button is no longer needed
        st.info("Your answers are now checked automatically after every change.")  # explain the live check

    result = None  # no result until the first check
    if st.session_state.get("checked"):  # checked at least once: show messages (no red on an empty form)
        result = evaluate(answers, knowledge)  # the engine checks everything and selects the clauses
        show_messages(result, message_areas, general_messages, knowledge)  # red and yellow messages with legal basis
        if result["can_generate"]:  # no errors
            show_review(result, knowledge)  # review screen
            offer_download(result, answers, knowledge)  # download button
        else:  # at least one error
            st.error(f"Please correct the {len(result['errors'])} problem(s) marked in red above.")  # summary
            st.button("Download contract (Word)", disabled=True)  # "Generate" disabled while errors exist
    show_sidebar(knowledge, result)  # the sidebar is drawn last, so it can count the problems per section


def show_sidebar(knowledge, result):
    """Show the sidebar: a link to every section and to "Check and review", so the user can jump without scrolling.

    Every section is a card (style: SIDEBAR_STYLE). After a check, a card shows a red badge with
    the number of problems in that section, or a green tick if there is none.
    Clicking a card scrolls to the section heading with the same anchor (see ask_questions).
    """
    checked = result is not None  # True after the first check
    cards = []  # the HTML of each card
    for section_id, section in knowledge["sections"].items():  # each questionnaire section
        problems = count_problems(section_id, result, knowledge)  # errors in this section (0 before a check)
        cards.append(nav_card(section["title"], section_id, problems, checked))  # one card
    cards.append(nav_card("Check and review", "check", 0, False))  # the last card: same look as the sections
    st.sidebar.subheader("Sections")  # sidebar heading
    st.sidebar.markdown(SIDEBAR_STYLE + "\n".join(cards), unsafe_allow_html=True)  # the style and the cards
    st.sidebar.divider()  # a line
    st.sidebar.caption(PROTOTYPE_NOTE)  # prototype note (law packet Task 13)


def nav_card(title, anchor, problems, checked):
    """Return the HTML of one sidebar card: a link to an anchor, with a badge on the right.

    Example: nav_card("Signature", "signature", 2, True) -> a white card "Signature" with a red "2".
    """
    if problems:  # this section has errors
        badge = f'<span class="nav-badge" title="{problems} to correct">{problems}</span>'  # red number
    elif checked:  # checked and no errors in this section
        badge = '<span class="nav-ok" title="no problems">✓</span>'  # green tick
    else:  # not checked yet
        badge = ""  # no badge
    return f'<a class="nav-item" href="#{anchor}" target="_self"><span>{html.escape(title)}</span>{badge}</a>'  # the card


def count_problems(section_id, result, knowledge):
    """Return how many errors belong to questions of one section (0 if there is no result yet)."""
    if result is None:  # not checked yet
        return 0  # nothing to count
    count = 0  # errors found in this section
    for error in result["errors"]:  # each error
        field = knowledge["fields"].get(error["field"])  # the question it belongs to (None for e.g. R_CROSS)
        if field is not None and field["section"] == section_id:  # it belongs to this section
            count += 1  # count it
    return count  # e.g. 2


# ---------------------------------------------------------------------------
# Questionnaire
# ---------------------------------------------------------------------------

def ask_questions(knowledge):
    """Show every active question, section by section, and return (answers, message_areas).

    answers:       {field_id: answer} of the questions shown
    message_areas: {field_id: place directly below the question} for the messages
    A question is only shown when it is active (parameters.yaml "active_when"), e.g.
    estimate_basis only for an estimate. Fields are asked in the order of parameters.yaml,
    so the answer a condition depends on (price_type) is known before the dependent question.
    """
    answers = {}  # the answers, filled below
    message_areas = {}  # the places for the messages, filled below
    for section_id, section in knowledge["sections"].items():  # each section of the questionnaire
        st.header(section["title"], anchor=section_id)  # section heading; the anchor is the target of the sidebar link
        for field_id, field in knowledge["fields"].items():  # each field, in file order
            if field["section"] != section_id:  # the field belongs to another section
                continue  # skip it here
            if not is_active(field_id, answers, knowledge):  # not needed for these answers
                continue  # do not show it
            answers[field_id] = ask(field, answers)  # show the question and keep the answer
            message_areas[field_id] = st.container()  # an empty place right below the question
    return answers, message_areas  # everything the rest of the page needs


def ask(field, answers):
    """Show one question with the right input element for its type and return the answer.

    Nothing is preselected: an unanswered question returns None (handoff App. B).
    Money is returned as Decimal (D25).
    """
    label = question_text(field, answers)  # the question, maybe depending on another answer
    help_text = field.get("help_text")  # shown behind the small "?" (optional)
    key = field["id"]  # Streamlit remembers the answer under this key between clicks
    field_type = field["type"]  # the data type from parameters.yaml
    if field_type == "date":  # a calendar date
        return st.date_input(label, value=None, format="DD.MM.YYYY", help=help_text, key=key)  # None until chosen
    if field_type == "enum":  # one answer from a list
        labels = {option["value"]: option["label"] for option in field["allowed_values"]}  # stored value -> text
        return st.radio(label, list(labels), index=None, format_func=labels.get, help=help_text, key=key)  # None until chosen
    if field_type == "boolean":  # yes / no
        return st.radio(label, [True, False], index=None, format_func=YES_NO.get, horizontal=True,
                        help=help_text, key=key)  # None until chosen; False = answered "no"
    if field_type == "text":  # one line of text
        return st.text_input(label, help=help_text, key=key)  # "" until typed
    if field_type == "long_text":  # several lines of text
        return st.text_area(label, help=help_text, key=key)  # "" until typed
    if field_type == "decimal_chf":  # money
        amount = st.number_input(label, value=None, step=0.01, format="%.2f", help=help_text, key=key)  # a float or None
        return None if amount is None else Decimal(str(amount))  # turn it into an exact Decimal (D25)
    if field_type == "integer":  # whole number
        return st.number_input(label, value=None, step=1, help=help_text, key=key)  # an int or None
    if field_type == "list":  # a table such as milestones or annexes
        return ask_table(field, label, help_text, key)  # see below
    raise ValueError(f"no input element for field type '{field_type}'")  # a new type needs a new element here


def question_text(field, answers):
    """Return the question text; some questions change with another answer (parameters.yaml "question_variants").

    Example: contract_price asks "What is the fixed total?" once price_type = fixed.
    """
    depends_on = field.get("question_depends_on")  # e.g. "price_type", or None
    if depends_on is None:  # the question never changes
        return field["question"]  # the normal question
    variant = field["question_variants"].get(answers.get(depends_on))  # the variant for the current answer
    return variant or field["question"]  # the normal question while the other answer is still missing


# ---------------------------------------------------------------------------
# Tables (milestones, technical annexes)
# ---------------------------------------------------------------------------

def ask_table(field, label, help_text, key):
    """Show an editable table (rows can be added with "+") and return its rows as a list of dictionaries.

    The table starts with one empty row; completely empty rows are left out of the answer.
    """
    st.markdown(f"**{label}**", help=help_text)  # the question above the table
    columns = field["columns"]  # the column definitions from parameters.yaml
    empty_row = {column["id"]: column.get("default") for column in columns}  # one empty row (with defaults)
    config = {column["id"]: table_column(column) for column in columns}  # how each column is edited
    rows = st.data_editor([empty_row], column_config=config, num_rows="dynamic", hide_index=True, key=key)  # the table
    return clean_rows(rows, columns)  # the rows in the types the engine expects


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


# ---------------------------------------------------------------------------
# Messages, review screen and download
# ---------------------------------------------------------------------------

def show_messages(result, message_areas, general_messages, knowledge):
    """Show every error (red) and warning (yellow) right below its question, with its legal basis.

    Messages without a question (e.g. W_CONSUMER, or R_CROSS which names a slot)
    are shown at the top of the page.
    """
    for error in result["errors"]:  # each error
        place = message_areas.get(error["field"], general_messages)  # below its question, else at the top
        place.error(message_with_basis(error, knowledge))  # red box: message + legal basis
    for warning in result["warnings"]:  # each warning (also shown when there are errors, D18)
        place = message_areas.get(warning["field"], general_messages)  # below its question, else at the top
        place.warning(message_with_basis(warning, knowledge))  # yellow box: message + legal basis


def message_with_basis(entry, knowledge):
    """Return an error or warning message followed by its legal basis, as Markdown.

    Rules without citations (e.g. R_REQUIRED, a pure PRODUCT rule) show only the message.
    """
    if not entry["citations"]:  # no legal basis (law packet: "no statutory rule asserted")
        return entry["message"]  # only the message
    return entry["message"] + "\n\n" + legal_basis(entry["citations"], knowledge)  # message, empty line, legal basis


def legal_basis(citation_ids, knowledge):
    """Return "Legal basis:" and one line per citation, as Markdown (the same look for clauses, errors and warnings)."""
    lines = [f"- {citation_line(citation_id, knowledge)}" for citation_id in citation_ids]  # one bullet per citation
    return "**Legal basis:**\n" + "\n".join(lines)  # heading and bullets


def citation_line(citation_id, knowledge):
    """Return one citation as Markdown: label with link, summary, source title and extra links.

    The label links to the legal text itself. Extra links: the English translation
    for the German Code of Obligations (S1 -> reading aid S2), and the SECO guidance
    next to the UWG on Fedlex (S4, law packet Task 1: "the statute is the legal source").
    Example: "[Art. 374 CO](...): no fixed price means ... (Swiss Code of Obligations SR 220) · [English translation](...)"
    """
    citation = knowledge["citations"][citation_id]  # from sources.yaml, e.g. CO_374
    source = knowledge["sources"][citation["source"]]  # the document it is in, e.g. S1
    law_url = source.get("url_statutory_text") or source["url"]  # the statute itself if a separate link exists
    line = f"[{citation['label']}]({law_url}): {citation['summary']} ({source['title']})"  # the main part
    if source.get("url_statutory_text"):  # S4: the statute link is above, the guidance is the normal url
        line += f" · [guidance]({source['url']})"  # link to the SECO guidance
    if source.get("reading_aid"):  # S1: German original; S2 is the English reading aid
        line += f" · [English translation]({knowledge['sources'][source['reading_aid']]['url']})"  # link to S2
    return line  # one Markdown line


def show_review(result, knowledge):
    """Show the review screen: every selected clause with its reason, legal basis, version and text.

    Legal sources are shown here (and next to the messages), never in the contract (handoff App. C).
    """
    st.header("Review")  # review screen heading
    st.caption(f"Legal basis version: {result['law_version']}")  # law_version (handoff App. C)
    current_topic = None  # the topic of the clause shown before (none yet)
    for record in result["selected_clauses"]:  # each selected clause, already sorted by topic (engine.py)
        if record["topic_id"] != current_topic:  # the first clause of a new topic
            current_topic = record["topic_id"]  # remember the topic
            st.subheader(knowledge["topics"][current_topic]["name"])  # topic heading, e.g. "Price and payment"
        title = f"{record['title']} ({record['clause_id']}, version {record['clause_version']})"  # e.g. "Fixed price (PRICE_FIXED, version 1.1)"
        with st.expander(title, expanded=True):  # a box that can be folded
            st.markdown(f"**Reason:** {record['reason']}")  # plain-language reason (law packet Task 10)
            st.caption(f"Selected by rule {record['selection_rule_id']}")  # the rule ID
            st.markdown(legal_basis([c["citation_id"] for c in record["citations"]], knowledge))  # the citations
            if record["basis_note"]:  # the App. D "Basis" line
                st.caption(record["basis_note"])  # e.g. "... written change process is a product choice."
            if record["warnings"]:  # warnings of the same topic (D28)
                st.caption("Related warnings: " + ", ".join(record["warnings"]))  # e.g. "W_PRICE"
            st.markdown("**Clause text:**")  # the filled clause
            st.text(record["text"])  # st.text keeps the line breaks of the milestone schedule
    if result["warnings"]:  # all warnings once more before the download (diagrams PDF ch. 1, step 4)
        st.subheader("Warnings")  # heading
        for warning in result["warnings"]:  # each warning
            st.warning(f"**{warning['rule_id']}:** " + message_with_basis(warning, knowledge))  # rule ID, message, legal basis
    if result["ignored_fields"]:  # answers the engine ignored (e.g. old milestones)
        st.caption("Ignored answers (not used for these choices): " + ", ".join(result["ignored_fields"]))  # list them


def offer_download(result, answers, knowledge):
    """Build the Word contract and show the download button (or the generator's message if it refuses)."""
    try:  # the generator refuses with GenerationError if something is wrong
        word_bytes = generate_contract(result, answers, knowledge)  # the Word file as bytes
    except GenerationError as error:  # it refused
        st.error(str(error))  # show why
        return  # no download
    st.download_button("Download contract (Word)", data=word_bytes, file_name="construction_contract.docx",
                       mime=WORD_FILE_TYPE, type="primary")  # clicking it downloads the file


main()  # Streamlit runs this file from top to bottom on every click
