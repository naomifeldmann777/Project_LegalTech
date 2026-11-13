"""app.py - the Streamlit user interface of the Construction Contract Generator.

What this file is for:
    It guides the user step by step through the questionnaire (one step per section of
    parameters.yaml), checks the answers with the engine, shows errors (red) and warnings
    (yellow), shows the review screen and offers the Word contract for download. The review
    screen shows the annotated contract (the generated contract like a sheet of paper, each
    chosen clause highlighted with a "Why ...?" explanation), the clauses grouped by topic and
    the legal sources, which can be checked on Fedlex (law_check.py): is the official text of
    each cited article still the same today as in the version the contract is based on?
    The flow follows the process flowchart (diagrams PDF ch. 1):
        step 1 ... step 8 (questions) -> last step "Check and review"
            -> errors: listed per step; "Go to this step" leads back to the questions
            -> no errors: review screen -> download
    The engine checks the answers after every change. Errors and warnings are shown directly
    below the questions: a wrong answer at once, a missing answer only after the user has
    left its step (so a fresh form is not full of red), and everything after the first visit
    of "Check and review" (see visible_errors).

How it fits into the project:
    Start it from the project root with:   streamlit run app.py
    This file only shows and collects; it contains no rule logic (AI_PROMPT section 6):
      - the questions and the steps come from data/parameters.yaml (via data_loader.py)
      - which questions are shown comes from "active_when" (engine.is_active)
      - all checks, clause choices and texts come from engine.evaluate()
      - the Word file comes from generator.generate_contract()
    The YAML files are loaded once; restart the app after changing a YAML file.
    The sidebar lists every step with its status; the colours are set in .streamlit/config.toml.

How the answers survive a change of step:
    Streamlit forgets the value of an input element that is not drawn, and only one step is
    drawn at a time. set_up_state() therefore hands every answer back to Streamlit at the start
    of each run (st.session_state[key] = st.session_state[key]), which makes Streamlit keep it.
    Tables cannot be kept like this; their cleaned rows are stored in st.session_state["tables"]
    and the table is drawn again from there when the user comes back to its step.

Which documents it implements:
    AI_PROMPT step 17 (questionnaire with only active fields, milestones as a table,
    red errors next to the fields, yellow warnings, review screen, "Generate" disabled
    while errors exist, download button), diagrams PDF ch. 1 (user flow), handoff
    App. B (None = not answered: no answer is preselected), App. C (sources only on
    the review screen), law packet Task 13 (prototype note), decisions D18, D25, D28.
"""

from datetime import date, datetime  # date answers; datetime to recognise date-times from the table
from decimal import Decimal  # money and percentages become exact Decimal values (D25)
import html  # html.escape: contract text is written safely into the preview's HTML
from io import BytesIO  # read the generated Word file from memory

from docx import Document  # python-docx: reads the generated Word file back for the contract preview
from docx.enum.text import WD_ALIGN_PARAGRAPH  # to recognise centred paragraphs
from docx.table import Table  # a table in the Word file (parties, signatures)
import streamlit as st  # the web user interface

from checks import is_empty  # the definition of "not answered" (None, "", [])
from data_loader import load_knowledge  # reads and checks the YAML files
from engine import evaluate, is_active  # the rule engine and "is this question shown?"
from generator import GenerationError, generate_contract  # builds the Word file
from law_check import FedlexError, check_citations, download  # checks the cited articles on Fedlex


# law packet Task 13: the prototype note (same text as below the contract title)
PROTOTYPE_NOTE = ("Academic prototype for seminar demonstration. This document may contain incomplete sections "
                  "and requires completion and legal review before use.")
YES_NO = {True: "Yes", False: "No"}  # how true / false answers are shown (questions and table cells)
TABLE_YES_NO = {"Yes": True, "No": False}  # the yes/no choice inside a table, turned back into true / false
WORD_FILE_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # file type of .docx
REVIEW_TITLE = "Check and review"  # title of the last step (it has no section in parameters.yaml)
DECIMAL_TYPES = ("decimal_chf", "decimal_percent")  # answers that become exact Decimal values (D25)
EMPTY_ANSWERS = {"text": "", "long_text": "", "enum_list": []}  # "not answered" per type; every other type: None
ONE_DAY = 24 * 60 * 60  # seconds; the Fedlex texts are loaded at most once a day
# demo of the Fedlex check: the check pretends that the law in force today were the version of this
# day (before the revision of the defect rules for building works of 1 January 2026), so that real
# changed articles can be shown; the contract's own basis (law_version) stays the same
DEMO_TODAY = date(2025, 10, 1)
# how the result of the Fedlex check is shown in the title of a source (coloured icon and word)
CHECK_LABELS = {"unchanged": ":green[:material/check_circle:] unchanged",  # the same text today
                "changed": ":orange[:material/warning:] changed",  # the text differs today
                "missing": ":red[:material/cancel:] no longer in force",  # not in today's version
                "not_checkable": ":gray[:material/gavel:] court decision"}  # not on Fedlex

# small changes to Streamlit's look; the colours themselves are in .streamlit/config.toml.
# The step buttons have keys like "step_ok_2"; Streamlit gives each a class "st-key-step_ok_2",
# so the status (open / ok / error) in the key decides the colour of the icon.
PAGE_STYLE = """
<style>
[class*="st-key-step_"] button > div,                  /* the box inside a step button */
[class*="st-key-step_"] button > div > span {          /* the box around icon and title */
  justify-content: flex-start;                         /* icon and title start on the left, like a menu */
}
[class*="st-key-step_"] button p {                     /* the title */
  text-align: left;                                    /* a long title also wraps on the left */
}
[class*="st-key-step_ok_"] [data-testid="stIconMaterial"] { color: #2E7D32; }     /* green tick */
[class*="st-key-step_error_"] [data-testid="stIconMaterial"] { color: #B42318; }  /* red mark */
[class*="st-key-step_open_"] [data-testid="stIconMaterial"] { color: #8A8170; }   /* grey circle */
/* the current step is a dark blue button: lighter colours, so the icon stays visible */
[class*="st-key-step_ok_"] [data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"] { color: #A5E3B4; }
[class*="st-key-step_error_"] [data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"] { color: #FFB3A8; }
[class*="st-key-step_open_"] [data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"] { color: #FFFFFF; }
.summary-row {                                         /* the two number cards on the review step */
  display: flex;                                       /* side by side */
  gap: 1rem;                                           /* space between the cards */
  margin-bottom: 0.5rem;                               /* space below the cards */
}
.summary-card {                                        /* one number card */
  flex: 1;                                             /* both cards equally wide */
  display: flex;                                       /* label, number and hint ... */
  flex-direction: column;                              /* ... below each other */
  padding: 0.75rem 1rem;                               /* space inside the card */
  background: #FFFFFF;                                 /* white card on the beige page */
  border: 1px solid #D6CCB8;                           /* thin beige border */
  border-radius: 0.6rem;                               /* rounded corners */
  color: #1A1A1A !important;                           /* dark text instead of a blue link */
  text-decoration: none !important;                    /* no underline */
  transition: background 0.15s, border-color 0.15s;    /* smooth colour change on hover */
}
a.summary-card:hover {                                 /* mouse over a card that is a link */
  background: #EEF3F8;                                 /* light blue */
  border-color: #1F4E79;                               /* dark blue border (primary colour) */
}
.summary-label { font-size: 0.875rem; color: #5C5648; }                  /* e.g. "Warnings" */
.summary-value { font-size: 2.25rem; font-weight: 600; line-height: 1.2; }  /* the number */
.summary-hint { font-size: 0.8rem; color: #1F4E79; }                    /* "Show ↓" */
.st-key-contract_paper {                               /* the contract preview: a white sheet of paper */
  background: #FFFFFF;                                 /* white like paper */
  border: 1px solid #D6CCB8;                           /* thin beige border */
  border-radius: 0.3rem;                               /* slightly rounded corners */
  padding: 2.5rem 2.75rem;                             /* page margins */
  box-shadow: 0 2px 14px rgba(0, 0, 0, 0.08);          /* soft shadow, as if the sheet lay on the page */
}
div.paper, div.paper p, div.paper table td {           /* all contract text */
  font-family: Georgia, "Times New Roman", serif;      /* the font of the Word contract */
  font-size: 0.95rem;                                  /* a little smaller than the app text */
  line-height: 1.55;                                   /* easy to read */
  color: #1A1A1A;                                      /* almost black */
}
div.paper p { margin: 0 0 0.6rem 0; text-align: justify; }  /* paragraphs: justified like the contract */
div.paper p.center { text-align: center; }                  /* centred lines below the title */
div.paper .paper-title {                               /* "Construction Contract" */
  font-size: 1.7rem; letter-spacing: 0.12em; text-transform: uppercase;  /* large, spaced capitals */
  color: #1F4E79; text-align: center; margin: 0.5rem 0 0.8rem;          /* dark blue, centred */
}
div.paper .paper-part {                                /* part headings, e.g. "Contract terms" */
  text-align: center; text-transform: uppercase; letter-spacing: 0.1em;  /* centred capitals */
  color: #1F4E79; font-weight: 600;                                      /* dark blue, semi-bold */
  border-top: 1px solid #B7C7D9; border-bottom: 1px solid #B7C7D9;      /* fine rules above and below */
  padding: 0.3rem 0; margin: 1.6rem 0 1rem;                              /* space around it */
}
div.paper .paper-heading {                             /* section headings, e.g. "5 Price and payment" */
  font-weight: 700; color: #1F4E79;                    /* bold, dark blue */
  border-bottom: 1px solid #B7C7D9;                    /* fine rule below */
  padding-bottom: 0.15rem; margin: 1.2rem 0 0.6rem;    /* space around it */
}
div.paper table { width: 100%; border-collapse: separate; border-spacing: 0; margin: 0.4rem 0 0.8rem; }  /* full width */
div.paper table td { vertical-align: top; padding: 0.5rem 0.7rem; border: none; }  /* no grid lines */
div.paper table.paper-parties td.filled { background: #EEF3F8; border: 1px solid #B7C7D9; }  /* boxes for the parties */
div.paper table td.sign-line { border-bottom: 1px solid #8A8170; padding-top: 1.6rem; }  /* line to sign on */
[class*="st-key-contract_clause_"] {                   /* a clause chosen by the rules */
  background: #EEF3F8;                                 /* light blue */
  border-left: 4px solid #1F4E79;                      /* dark blue bar on the left */
  border-radius: 0 0.3rem 0.3rem 0;                    /* rounded on the right */
  padding: 0.6rem 0.9rem 0.3rem;                       /* space inside */
  margin: 0.2rem 0 0.8rem;                             /* space to the fixed text */
}
</style>
"""


@st.cache_resource  # load the YAML files only once, not on every click
def get_knowledge():
    """Return the knowledge base (all four YAML files, checked by data_loader.py)."""
    return load_knowledge()  # stops with a clear message if a YAML file has a mistake


@st.cache_data(ttl=ONE_DAY, show_spinner=False)  # each Fedlex address is loaded at most once a day
def fetch_from_fedlex(url):
    """Return the bytes at a Fedlex address (kept for a day, so the check is fast after the first time)."""
    return download(url)  # law_check.download raises FedlexError without a connection


@st.cache_data(ttl=ONE_DAY, show_spinner=False)  # the same citations on the same day: the same result
def run_law_check(citation_ids, today):
    """Return the Fedlex check of these citations (law_check.check_citations), kept for a day."""
    return check_citations(list(citation_ids), get_knowledge(), today, fetch=fetch_from_fedlex)  # the check


# ---------------------------------------------------------------------------
# Main page and steps
# ---------------------------------------------------------------------------

def main():
    """Draw the page: progress, the current step (questions or "Check and review"), buttons and sidebar."""
    st.set_page_config(page_title="Construction Contract Generator", page_icon=":material/construction:")  # browser tab
    st.html(PAGE_STYLE)  # the small style changes (a style-only block takes no space on the page)
    knowledge = get_knowledge()  # the knowledge base
    steps = list(knowledge["sections"]) + [None]  # one step per section, then None = "Check and review"
    set_up_state(knowledge)  # remember the step and keep the answers of the steps not shown
    step = st.session_state["step"]  # the number of the step shown (0 = first step)
    section_id = steps[step]  # the section of this step (None on the last step)
    if section_id is None:  # the user opened "Check and review"
        st.session_state["checked"] = True  # from now on, check after every change and show the messages

    st.title("Construction Contract Generator")  # page title
    st.caption(PROTOTYPE_NOTE)  # prototype note (law packet Task 13)
    progress_area = st.empty()  # the progress bar; filled below, once the answers are known
    show_step_header(step, steps, knowledge)  # step number, heading and short explanation of the step

    answers, message_areas = ask_questions(knowledge, section_id)  # draws this step's questions; returns all answers
    result = evaluate(answers, knowledge)  # the engine checks everything after every change
    errors = visible_errors(result, answers, knowledge, steps)  # only the errors the user should see now
    with progress_area:  # draw into the place at the top
        show_progress(answers, errors, knowledge)  # answered required questions and open problems
    if section_id is None:  # the last step
        show_check_step(result, answers, knowledge, steps)  # problems per step, or review screen and download
    else:  # a question step
        show_messages(errors, result["warnings"], message_areas, knowledge)  # red and yellow messages below the questions
    show_navigation(step, len(steps))  # "Back" and "Next"
    show_sidebar(knowledge, steps, step, errors)  # drawn last, so it can count the problems per step


def set_up_state(knowledge):
    """Prepare st.session_state at the start of every run and keep the answers of the steps not shown.

    step:        the step shown (0 = first step)
    left_steps:  the numbers of the steps the user has already left (with "Next", "Back" or the sidebar)
    checked:     True after the first visit of "Check and review"; from then on, every error is shown
    tables:      {field_id: cleaned rows} of every table (milestones, annexes)
    table_base:  {field_id: rows a table was drawn with during this visit of its step}
    table_round: counts the changes of step; it is part of a table's key, so that a table
                 starts again from "tables" every time the user comes back to its step
    """
    st.session_state.setdefault("step", 0)  # start with the first step
    st.session_state.setdefault("left_steps", set())  # no step left yet
    st.session_state.setdefault("checked", False)  # not checked yet
    st.session_state.setdefault("tables", {})  # no table rows yet
    st.session_state.setdefault("table_base", {})  # no table drawn yet
    st.session_state.setdefault("table_round", 0)  # first visit
    for field_id, field in knowledge["fields"].items():  # each question
        if field["type"] != "list" and field_id in st.session_state:  # a normal question the user has seen
            st.session_state[field_id] = st.session_state[field_id]  # hand it back: Streamlit keeps it even if not drawn


def go_to(step):
    """Show another step (used by "Back", "Next", the sidebar and "Go to this step")."""
    st.session_state["left_steps"].add(st.session_state["step"])  # the step shown until now has been left
    st.session_state["step"] = step  # the step to show
    st.session_state["table_round"] += 1  # new keys for the tables of that step (see set_up_state)
    st.session_state["table_base"] = {}  # the tables are drawn again from their stored rows


def start_again(knowledge):
    """Delete every answer and go back to the first step ("Start a new contract" in the sidebar)."""
    for field_id, field in knowledge["fields"].items():  # each question
        if field["type"] != "list":  # tables are reset below
            st.session_state[field_id] = EMPTY_ANSWERS.get(field["type"])  # "not answered" ("" for text, None for others)
    st.session_state["tables"] = {}  # no table rows
    st.session_state["checked"] = False  # not checked any more
    go_to(0)  # first step; also draws the tables again, now empty
    st.session_state["left_steps"] = set()  # no step left yet (go_to has just added the old step)


def step_title(section_id, knowledge):
    """Return the title of a step, e.g. "Price and payment"; the last step is "Check and review"."""
    if section_id is None:  # the last step
        return REVIEW_TITLE  # it has no section in parameters.yaml
    return knowledge["sections"][section_id]["title"]  # the section title from parameters.yaml


def show_progress(answers, errors, knowledge):
    """Show a bar with the share of required questions answered, and the number of problems to correct.

    The bar measures answers, not steps: it only becomes full when every required question
    shown is answered, so it does not look finished while answers are missing. Only the
    questions active for the current answers count (parameters.yaml "required" and "active_when").
    Example text: "18 of 24 required questions answered · 1 problem to correct"
    """
    required = [field_id for field_id in answers if knowledge["fields"][field_id]["required"]]  # active and required
    answered = [field_id for field_id in required if not is_empty(answers[field_id])]  # of those: answered
    if len(answered) < len(required):  # something is still missing
        text = f"{len(answered)} of {len(required)} required questions answered"  # e.g. "18 of 24 ..."
    else:  # every required question is answered
        text = "All required questions answered"  # full bar
    if errors:  # visible problems (see visible_errors)
        text += f" · {len(errors)} problem{'s' if len(errors) != 1 else ''} to correct"  # e.g. " · 1 problem to correct"
    st.progress(len(answered) / len(required) if required else 1.0, text=text)  # the bar with its text


def show_step_header(step, steps, knowledge):
    """Show the step number, the heading of the step and its short explanation (parameters.yaml "intro")."""
    section_id = steps[step]  # the section of this step (None on the last step)
    st.caption(f"STEP {step + 1} OF {len(steps)}")  # where the user is, e.g. "STEP 3 OF 9"
    st.header(step_title(section_id, knowledge))  # e.g. "Price and payment"
    if section_id is None:  # the last step
        st.caption("All answers are checked together. Errors must be corrected; warnings are points to review.")
        return  # done
    intro = knowledge["sections"][section_id].get("intro")  # the short explanation, or None
    if intro:  # the section has one
        st.caption(intro)  # small grey text below the heading
    explanation = knowledge["sections"][section_id].get("explanation")  # the longer text for the Contractor, or None
    if explanation:  # e.g. step "Acceptance and defects"
        st.info(explanation, icon=":material/info:")  # blue box above the questions


def show_navigation(step, step_count):
    """Show "Back" on the left and "Next" (or "Check and review" before the last step) on the right."""
    with st.container(horizontal=True, horizontal_alignment="distribute"):  # the two buttons on one line, far apart
        st.button("Back", key="back_button", icon=":material/arrow_back:", disabled=step == 0,  # no step before the first
                  on_click=go_to, args=(step - 1,))  # one step back
        if step < step_count - 1:  # not on the last step yet
            label = REVIEW_TITLE if step == step_count - 2 else "Next"  # the last question step leads to the check
            st.button(label, key="next_button", type="primary", icon=":material/arrow_forward:", icon_position="right",
                      on_click=go_to, args=(step + 1,))  # one step forward


def show_sidebar(knowledge, steps, current, errors):
    """Show the sidebar: one button per step with its status, "Start a new contract" and the prototype note.

    Status of a question step (its colour comes from PAGE_STYLE through the button's key):
      error: red mark, the number of errors after the title - something to correct
      ok:    green tick - the step was left (or checked) and has no errors
      open:  grey empty circle - not finished yet, nothing wrong so far
    """
    st.sidebar.subheader("Steps")  # sidebar heading
    for number, section_id in enumerate(steps):  # each step, in order
        label = f"{number + 1} · {step_title(section_id, knowledge)}"  # e.g. "3 · Price and payment"
        problems = count_problems(section_id, errors, knowledge)  # errors shown for this step
        if section_id is None:  # the last step
            status, icon = "review", ":material/fact_check:"  # a checklist
        elif problems:  # something to correct
            status, icon = "error", ":material/error:"  # red mark
            label += f" ({problems})"  # e.g. "3 · Price and payment (2)"
        elif number in st.session_state["left_steps"] or st.session_state["checked"]:  # finished without errors
            status, icon = "ok", ":material/check_circle:"  # green tick
        else:  # not finished yet
            status, icon = "open", ":material/radio_button_unchecked:"  # grey empty circle
        st.sidebar.button(label, key=f"step_{status}_{number}", icon=icon, width="stretch",  # full width, like a menu
                          type="primary" if number == current else "secondary",  # the current step is dark blue
                          on_click=go_to, args=(number,))  # jump to this step
    st.sidebar.divider()  # a line
    with st.sidebar.popover("Start a new contract", icon=":material/restart_alt:", width="stretch"):  # asks first
        st.markdown("This deletes all answers.")  # explain what happens
        st.button("Delete all answers", type="primary", on_click=start_again, args=(knowledge,))  # confirm
    st.sidebar.caption(PROTOTYPE_NOTE)  # prototype note (law packet Task 13)


def section_of(entry, knowledge):
    """Return the section of the question an error or warning belongs to (None if it has no question)."""
    field = knowledge["fields"].get(entry["field"])  # the question (None for e.g. W_CONSUMER or R_CROSS)
    return None if field is None else field["section"]  # e.g. "price_payment"


def count_problems(section_id, errors, knowledge):
    """Return how many of the given errors belong to questions of one section."""
    return sum(1 for error in errors if section_of(error, knowledge) == section_id)  # e.g. 2


def visible_errors(result, answers, knowledge, steps):
    """Return the errors to show now, so that a fresh form is not full of red.

    An error is shown
      - at once if its question is already answered (e.g. a price of 0, a date in the past),
      - for an unanswered question only after the user has left its step,
      - always after the first visit of "Check and review".
    Errors without a question (e.g. R_CROSS) are shown on "Check and review" only.
    This only decides WHEN an error is shown; WHICH errors exist is decided by the engine.
    """
    if st.session_state["checked"]:  # "Check and review" was opened once
        return result["errors"]  # show everything
    shown = []  # the errors to show, filled below
    for error in result["errors"]:  # each error found by the engine
        section_id = section_of(error, knowledge)  # the section of its question (None if it has none)
        if section_id is None:  # not tied to a question
            continue  # only on "Check and review"
        step_left = steps.index(section_id) in st.session_state["left_steps"]  # the user has left this step
        if step_left or not is_empty(answers.get(error["field"])):  # step left, or the question is answered
            shown.append(error)  # show it
    return shown  # e.g. [] on a fresh form


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tables (milestones, technical annexes)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

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
    A court decision has its own link instead: its explanation, then "See court decision".
    Example: "[Art. 374 CO](...): no fixed price means ... (Swiss Code of Obligations SR 220) · [English translation](...)"
    Example: "BGE 115 II 460 (1989): the 10 % tolerance ... [See court decision](...)"
    """
    citation = knowledge["citations"][citation_id]  # from sources.yaml, e.g. CO_374
    if citation.get("url"):  # a court decision: it has its own link
        return f"{citation['label']}: {citation['summary']} [See court decision]({citation['url']})"  # one Markdown line
    source = knowledge["sources"][citation["source"]]  # the document it is in, e.g. S1
    law_url = source.get("url_statutory_text") or source["url"]  # the statute itself if a separate link exists
    line = f"[{citation['label']}]({law_url}): {citation['summary']} ({source['title']})"  # the main part
    if source.get("url_statutory_text"):  # S4: the statute link is above, the guidance is the normal url
        line += f" · [guidance]({source['url']})"  # link to the SECO guidance
    if source.get("reading_aid"):  # S1: German original; S2 is the English reading aid
        line += f" · [English translation]({knowledge['sources'][source['reading_aid']]['url']})"  # link to S2
    return line  # one Markdown line


# ---------------------------------------------------------------------------
# Last step: check, review screen and download
# ---------------------------------------------------------------------------

def show_check_step(result, answers, knowledge, steps):
    """Show the last step: the problems per step, or the summary, download and review screen."""
    word_bytes = None  # the Word contract; only built when there are no errors
    if result["can_generate"]:  # no errors
        st.success("No problems found. Your contract is ready.", icon=":material/task_alt:")  # green banner
        show_summary(result)  # two numbers: clauses and warnings
        word_bytes = offer_download(result, answers, knowledge)  # download button; the same file feeds the preview
    else:  # at least one error
        st.error(f"Please correct {len(result['errors'])} problem(s) before the contract can be created.",
                 icon=":material/error:")  # red banner with the number of errors
        show_errors_by_step(result, knowledge, steps)  # each step with its errors and a button to go there
        st.button("Download contract (Word)", disabled=True, icon=":material/download:",
                  width="stretch")  # "Generate" disabled while errors exist
    show_warnings(result, knowledge)  # warnings are shown in both cases (D18)
    if result["can_generate"]:  # the review screen only exists without errors
        show_review(result, knowledge, word_bytes)  # annotated contract and every clause with its reason and legal basis


def show_errors_by_step(result, knowledge, steps):
    """Show the errors grouped by step, each group in a card with a "Go to this step" button."""
    for number, section_id in enumerate(steps[:-1]):  # each question step (not the last step itself)
        errors = [error for error in result["errors"] if section_of(error, knowledge) == section_id]  # its errors
        if not errors:  # nothing to correct in this step
            continue  # no card
        with st.container(border=True):  # one card per step
            st.markdown(f"**Step {number + 1} · {step_title(section_id, knowledge)}**")  # e.g. "Step 3 · Price and payment"
            for error in errors:  # each error of this step
                st.error(message_with_basis(error, knowledge))  # red box: message + legal basis
            st.button("Go to this step", key=f"fix_step_{number}", icon=":material/edit:",
                      on_click=go_to, args=(number,))  # back to the questions of this step
    for error in result["errors"]:  # errors without a question (e.g. R_CROSS, which names a slot)
        if section_of(error, knowledge) is None:  # not tied to a step
            st.error(message_with_basis(error, knowledge))  # red box below the cards


def show_summary(result):
    """Show two numbers in small cards: the clauses that go into the contract and the warnings to review.

    Clicking a card scrolls further down ("Your contract" or "Warnings"), through the
    anchor of that heading (see show_review and show_warnings). The look is set in PAGE_STYLE.
    """
    cards = [summary_card("Clauses selected", len(result["selected_clauses"]), "contract"),  # e.g. 8
             summary_card("Warnings", len(result["warnings"]), "warnings")]  # e.g. 1
    st.markdown(f'<div class="summary-row">{"".join(cards)}</div>', unsafe_allow_html=True)  # both cards in one row


def summary_card(label, number, anchor):
    """Return the HTML of one number card: a link to the heading with this anchor, or a plain card for 0.

    Example: summary_card("Warnings", 1, "warnings") -> a card "Warnings 1 Show ↓" that scrolls to "Warnings".
    """
    inside = f'<span class="summary-label">{label}</span><span class="summary-value">{number}</span>'  # label and number
    if number == 0:  # nothing to show further down (e.g. no warnings: the list is not drawn)
        return f'<div class="summary-card">{inside}</div>'  # a card that is not a link
    hint = '<span class="summary-hint">Show ↓</span>'  # tells the user that the card can be clicked
    return f'<a class="summary-card" href="#{anchor}" target="_self">{inside}{hint}</a>'  # the card as a link


def show_warnings(result, knowledge):
    """Show every warning once more before the download (diagrams PDF ch. 1, step 4)."""
    if not result["warnings"]:  # no warnings
        return  # nothing to show
    st.subheader("Warnings", anchor="warnings")  # heading; the anchor is the target of the "Warnings" card
    for warning in result["warnings"]:  # each warning
        st.warning(f"**{warning['rule_id']}:** " + message_with_basis(warning, knowledge))  # rule ID, message, legal basis


def show_review(result, knowledge, word_bytes):
    """Show the review screen in three tabs: the annotated contract, the clauses by topic and the legal sources.

    Legal sources are shown here (and next to the messages), never in the contract (handoff App. C).
    """
    st.subheader("Your contract", anchor="contract")  # heading; target of the "Clauses selected" card
    st.caption(f"Why each clause was chosen and on which legal basis. Legal basis version: {result['law_version']}")
    annotated, by_topic, sources = st.tabs(["Annotated contract", "Clauses by topic", "Legal sources"])  # three views
    with annotated:  # the contract as it will be downloaded, with explanations
        if word_bytes is None:  # the generator refused (its message is shown above)
            st.info("The contract preview is not available because the contract could not be created.")  # explain
        else:  # the contract exists
            show_annotated_contract(word_bytes, result, knowledge)  # the sheet of paper
    with by_topic:  # one tab per topic with the clause cards
        records = result["selected_clauses"]  # already sorted by topic (engine.py)
        topic_ids = list(dict.fromkeys(record["topic_id"] for record in records))  # the topics, in contract order
        tabs = st.tabs([knowledge["topics"][topic_id]["name"] for topic_id in topic_ids])  # one tab per topic
        for tab, topic_id in zip(tabs, topic_ids):  # each tab with its topic
            with tab:  # draw into this tab
                for record in records:  # each selected clause
                    if record["topic_id"] == topic_id:  # it belongs to this topic
                        show_clause(record, knowledge)  # the clause card
    with sources:  # every legal source of this contract, with the Fedlex check
        show_legal_sources(result, knowledge)  # see below
    if result["ignored_fields"]:  # answers the engine ignored (e.g. old milestones)
        st.caption("Ignored answers (not used for these choices): " + ", ".join(result["ignored_fields"]))  # list them


def show_clause(record, knowledge):
    """Show one selected clause: first the filled text, then its legal basis, then the reason it was chosen.

    The clause ID, its version, the selection rule and the IDs of related warnings are not
    shown, so as not to confuse the user; they stay in the engine's review record (engine.py)
    for the tests and the team. The warnings themselves are listed above the clauses.
    """
    with st.expander(record["title"], expanded=True):  # a box that can be folded, e.g. "Fixed price"
        st.markdown("**Clause text:**")  # label above the clause, like "Legal basis:" and "Reason:"
        st.text(record["text"])  # the filled clause; st.text keeps the line breaks of the milestone schedule
        st.markdown(legal_basis([c["citation_id"] for c in record["citations"]], knowledge))  # the citations
        if record["basis_note"]:  # the App. D "Basis" line
            st.caption(record["basis_note"])  # e.g. "... written change process is a product choice."
        st.markdown(f"**Reason:** {record['reason']}")  # plain-language reason (law packet Task 10)


# ---------------------------------------------------------------------------
# Annotated contract (review screen)
# ---------------------------------------------------------------------------

def show_annotated_contract(word_bytes, result, knowledge):
    """Show the generated contract like a sheet of paper; each clause chosen by the rules is highlighted
    and has a "Why ...?" button with the answers, the reason and the legal basis.

    The contract is read back from the same Word file the user downloads, so the preview always
    matches the download. A paragraph is a chosen clause when its text is exactly the filled text
    of a selected clause (engine review record); everything else is the fixed text of the template.
    """
    st.caption("Highlighted paragraphs were chosen by the rules from your answers; the rest is the fixed "
               "contract text. Click “Why …?” below a highlighted paragraph to see why it is there.")  # how to read it
    clauses = {record["text"].strip(): record for record in result["selected_clauses"]}  # clause text -> record
    document = Document(BytesIO(word_bytes))  # the Word file, read back
    waiting = []  # HTML of fixed text not drawn yet (drawn together, so the page needs few elements)
    tables_seen = 0  # the first table (section 1) holds the parties boxes, the last one the signatures
    with st.container(key="contract_paper", gap=None):  # the sheet of paper (look: PAGE_STYLE)
        for item in document.iter_inner_content():  # paragraphs and tables, in document order
            if isinstance(item, Table):  # the parties boxes or the signature block
                waiting.append(table_html(item, parties=tables_seen == 0))  # boxes only for the first table
                tables_seen += 1  # one more table seen
                continue  # next item
            record = clauses.get(item.text.strip())  # the clause this paragraph is, or None
            if record is None:  # fixed text of the template
                waiting.append(paragraph_html(item))  # keep it for later
                continue  # next item
            draw_paper(waiting)  # first the fixed text before the clause
            waiting = []  # all drawn
            show_contract_clause(item, record, knowledge)  # the highlighted clause with its "Why ...?" button
        draw_paper(waiting)  # the fixed text after the last clause


def draw_paper(parts):
    """Draw collected HTML parts of the contract (nothing if there are none)."""
    if parts:  # something to draw
        st.markdown(f'<div class="paper">{"".join(parts)}</div>', unsafe_allow_html=True)  # one block of contract text


def runs_html(paragraph):
    """Return the text of a Word paragraph as HTML, keeping bold, italics and line breaks.

    Example: a run "Client:" in bold -> "<strong>Client:</strong>"
    """
    pieces = []  # the HTML of each run
    for run in paragraph.runs:  # each piece of text with one format
        text = html.escape(run.text).replace("\n", "<br>")  # safe text; a line break in Word becomes <br>
        if run.bold:  # bold in Word
            text = f"<strong>{text}</strong>"  # bold here
        if run.italic:  # italics in Word
            text = f"<em>{text}</em>"  # italics here
        pieces.append(text)  # keep it
    return "".join(pieces)  # e.g. "<strong>Contract date:</strong> 1 November 2026"


def paragraph_html(paragraph):
    """Return one paragraph of fixed contract text as HTML, styled by its Word style ("" if it is empty)."""
    text = runs_html(paragraph)  # the text with its formats
    if not text.strip():  # an empty paragraph (spacing in Word)
        return ""  # leave it out
    style = paragraph.style.name  # the Word style, e.g. "Heading 2"
    if style == "Title":  # "Construction Contract"
        return f'<div class="paper-title">{text}</div>'  # large, centred
    if style == "Heading 1":  # part heading, e.g. "Contract terms"
        return f'<div class="paper-part">{text}</div>'  # centred capitals between two rules
    if style == "Heading 2":  # section heading, e.g. "5 Price and payment"
        return f'<div class="paper-heading">{text}</div>'  # bold, dark blue
    centred = paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER  # e.g. the lines below the title
    return f'<p class="{"center" if centred else ""}">{text}</p>'  # a normal paragraph


def table_html(table, parties):
    """Return a Word table (parties boxes or signature block) as an HTML table.

    parties=True draws the filled cells as boxes; a cell ending with ":" (e.g. "Signature:")
    gets a line to sign on, like in the Word file.
    """
    rows = []  # the HTML of each row
    for row in table.rows:  # each row
        cells = []  # the HTML of each cell
        for cell in row.cells:  # each cell (the middle one is an empty spacer)
            inner = "<br>".join(runs_html(p) for p in cell.paragraphs if p.text.strip())  # its lines
            classes = []  # how the cell looks
            if parties and inner:  # a party box with text
                classes.append("filled")  # light blue box
            if cell.text.strip().endswith(":"):  # e.g. "Signature:" or "Place and date:"
                classes.append("sign-line")  # a line to sign on
            cells.append(f'<td class="{" ".join(classes)}">{inner}</td>')  # the cell
        rows.append(f"<tr>{''.join(cells)}</tr>")  # the row
    kind = "paper-parties" if parties else "paper-signatures"  # which kind of table
    return f'<table class="{kind}">{"".join(rows)}</table>'  # the table


def show_contract_clause(paragraph, record, knowledge):
    """Show one chosen clause highlighted, with a "Why ...?" button that opens the explanation."""
    with st.container(key=f"contract_clause_{record['position']}", gap=None):  # light blue box (PAGE_STYLE)
        st.markdown(f'<div class="paper"><p>{runs_html(paragraph)}</p></div>', unsafe_allow_html=True)  # the clause
        with st.popover(f"Why “{record['title']}”?", icon=":material/help:", type="tertiary"):  # closes on a click outside
            show_why(record, knowledge)  # the explanation


def show_why(record, knowledge):
    """Show why a clause is in the contract: reason, the answers it is based on, and its legal basis."""
    st.markdown(f"**{record['title']}**")  # e.g. "Fixed price"
    st.markdown(f"**Reason:** {record['reason']}")  # plain-language reason (law packet Task 10)
    used = {**record["decided_by"], **record["input_values"]}  # answers that chose it, then answers it uses
    if used:  # the clause depends on answers
        lines = [f"- {knowledge['fields'][field_id]['question']} **{answer_text(knowledge['fields'][field_id], value)}**"
                 for field_id, value in used.items()]  # one bullet per answer: question and answer
        st.markdown("**Based on your answers:**\n" + "\n".join(lines))  # the list
    st.markdown(legal_basis([c["citation_id"] for c in record["citations"]], knowledge))  # the citations
    if record["basis_note"]:  # the App. D "Basis" line
        st.caption(record["basis_note"])  # e.g. "... written change process is a product choice."


def answer_text(field, value):
    """Return an answer as short readable text for the "Why ...?" explanation.

    Examples: "fixed" -> "Fixed price"; True -> "Yes"; Decimal("100000") -> "CHF 100,000.00"; 3 rows -> "3 rows"
    """
    if is_empty(value):  # not answered (e.g. no maximum for a delay penalty)
        return "not answered"  # say so
    field_type = field["type"]  # the data type from parameters.yaml
    if field_type == "boolean":  # yes / no
        return YES_NO[value]  # "Yes" / "No"
    if field_type in ("enum", "enum_list"):  # chosen from a list
        labels = {option["value"]: option["label"] for option in field["allowed_values"]}  # stored value -> text
        chosen = value if field_type == "enum_list" else [value]  # always a list here
        return ", ".join(labels.get(item, str(item)) for item in chosen)  # e.g. "Fixed price"
    if field_type == "date":  # a date
        return value.strftime("%d.%m.%Y")  # e.g. "30.06.2027"
    if field_type == "decimal_chf":  # money
        return f"CHF {value:,.2f}"  # e.g. "CHF 100,000.00"
    if field_type == "decimal_percent":  # a percentage
        return f"{value:,.2f} %"  # e.g. "5.00 %"
    if field_type == "list":  # a table such as the milestones
        return f"{len(value)} row{'s' if len(value) != 1 else ''}"  # e.g. "3 rows"
    return " ".join(str(value).split())  # text or number on one line (line breaks would break the list)


# ---------------------------------------------------------------------------
# Legal sources and the Fedlex check (review screen)
# ---------------------------------------------------------------------------

def show_legal_sources(result, knowledge):
    """Show every legal source this contract relies on; "Check on Fedlex" adds the official text of each article
    and whether it still reads the same today as in the version the contract is based on (law_check.py).
    """
    used = used_citations(result)  # citation ID -> where it is used
    basis = date.fromisoformat(str(knowledge["law_version"]))  # the version the texts are based on
    st.caption(f"The {len(used)} legal sources this contract relies on. “Check on Fedlex” loads the official text "
               f"of each article from the Swiss federal law database and checks whether it still reads the same "
               f"today as in the version your contract is based on ({basis:%d.%m.%Y}). Needs an internet connection.")
    if st.button("Check on Fedlex", key="law_check_button", icon=":material/sync:", type="primary"):  # the user asks
        st.session_state["law_check_on"] = True  # from now on, show the check (also after other clicks)
    demo = st.toggle("Demo: simulate a change in the law", key="law_check_demo")  # off by default
    if demo:  # make clear that the law in force is simulated
        st.caption(f"For demonstration only: the check pretends that the law in force today were the version of "
                   f"{DEMO_TODAY:%d.%m.%Y}, which differs from the version of {basis:%d.%m.%Y} your contract is "
                   f"based on in the defect rules for building works (revised on 1 January 2026). This shows how "
                   f"a change in the law is reported.")  # explain the demo
    report = None  # no check yet
    if st.session_state.get("law_check_on") or demo:  # the user asked for the check (switching on the demo asks too)
        try:  # Fedlex may not be reachable
            with st.spinner("Loading the law texts from Fedlex …"):  # the first time takes a few seconds
                report = run_law_check(tuple(used), DEMO_TODAY if demo else date.today())  # kept for a day
        except FedlexError as error:  # no connection or an unexpected answer
            st.error(f"Fedlex could not be reached ({error}). Check the internet connection and try again.")  # say so
    if report:  # the check has run
        show_check_summary(report, demo)  # one line: all unchanged, or how many changed
    for citation_id, places in used.items():  # each source, in the order of the contract
        show_source(citation_id, places, report, knowledge, demo)  # one expandable box


def used_citations(result):
    """Return {citation_id: [where it is used]} for the selected clauses and the warnings, in contract order.

    Example: {"CO_374": ["Estimated price", "Milestone payments"], "CO_163": ["warning W_PEN"], ...}
    """
    used = {}  # filled below; a dictionary keeps the order of the first use
    for record in result["selected_clauses"]:  # each clause in the contract
        for citation in record["citations"]:  # each source of the clause
            used.setdefault(citation["citation_id"], []).append(record["title"])  # used by this clause
    for warning in result["warnings"]:  # each warning
        for citation_id in warning["citations"]:  # each source of the warning
            used.setdefault(citation_id, []).append(f"warning {warning['rule_id']}")  # used by this warning
    return used  # e.g. 25 citations


def show_check_summary(report, demo):
    """Show one line above the sources: every checked article unchanged, or how many changed."""
    checked = [entry for entry in report.values() if entry["status"] != "not_checkable"]  # statutes only
    changed = [entry for entry in checked if entry["status"] != "unchanged"]  # changed or missing
    in_force = "in force today (simulated)" if demo else "in force today"  # the demo says that it simulates
    if changed:  # something to review
        st.warning(f"{len(changed)} of {len(checked)} cited statute texts {in_force} differ from the version your "
                   f"contract is based on. Have the clauses that use them reviewed.", icon=":material/warning:")
    else:  # everything the same
        st.success(f"All {len(checked)} cited statute texts {in_force} read the same as in the version your "
                   f"contract is based on.", icon=":material/verified:")  # green box


def show_source(citation_id, places, report, knowledge, demo):
    """Show one legal source as an expandable box: summary and links, where it is used and, after the check,
    the official text (and the text in force today if it has changed). Changed sources open by themselves.
    """
    citation = knowledge["citations"][citation_id]  # from sources.yaml
    check = report.get(citation_id) if report else None  # the check of this source, or None
    title = citation["label"] + (f" · {CHECK_LABELS[check['status']]}" if check else "")  # e.g. "Art. 374 CO · ✓ unchanged"
    with st.expander(title, expanded=bool(check) and check["status"] in ("changed", "missing")):  # a foldable box
        st.markdown(citation_line(citation_id, knowledge))  # summary and links (the same line as elsewhere)
        st.caption("Used in: " + ", ".join(dict.fromkeys(places)))  # e.g. "Used in: Fixed price, warning W_PRICE"
        if check is not None:  # the check has run
            show_check_texts(check, demo)  # the official text(s)


def show_check_texts(check, demo):
    """Show the official German text of one source as the Fedlex check found it (demo: the law in force is simulated)."""
    status = check["status"]  # e.g. "unchanged"
    if status == "not_checkable":  # a court decision
        st.caption("Court decisions are not in the federal law database and cannot be checked automatically.")
        return  # nothing more
    our_date = f"{check['our_version']:%d.%m.%Y}"  # e.g. "01.10.2026"
    today_date = f"{check['today_version']:%d.%m.%Y}" + (", simulated" if demo else "")  # e.g. "01.10.2026"
    if status == "unchanged":  # the same text
        st.markdown(f"**Official text in force today** (version of {today_date}; the same as in the version "
                    f"of {our_date} your contract is based on):")  # one text is enough
        st.text(check["today_text"])  # the article(s), paragraph by paragraph
    elif status == "changed":  # the text differs
        st.markdown(f"**Text your contract is based on** (version of {our_date}):")  # the contract's basis
        st.text(check["our_text"])  # that text
        st.markdown(f"**Text in force today** (version of {today_date}):")  # the law in force
        st.text(check["today_text"])  # that text
    else:  # missing: not in the version in force
        st.markdown(f"**This text is not in the version in force today** (version of {today_date}). "
                    f"Text your contract is based on (version of {our_date}):")  # explain
        st.text(check["our_text"] or "(not found)")  # the contract's text, if there is one
    st.caption("Official German text from Fedlex; footnotes are left out.")  # where the text comes from


def offer_download(result, answers, knowledge):
    """Build the Word contract, show the download button and return the file (None if the generator refuses)."""
    try:  # the generator refuses with GenerationError if something is wrong
        word_bytes = generate_contract(result, answers, knowledge)  # the Word file as bytes
    except GenerationError as error:  # it refused
        st.error(str(error))  # show why
        return None  # no download, no preview
    st.download_button("Download contract (Word)", data=word_bytes, file_name="construction_contract.docx",
                       mime=WORD_FILE_TYPE, type="primary", icon=":material/download:",
                       width="stretch")  # a wide button; clicking it downloads the file
    return word_bytes  # the same file for the contract preview


main()  # Streamlit runs this file from top to bottom on every click
