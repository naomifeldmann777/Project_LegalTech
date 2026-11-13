"""ui/navigation.py - steps, progress bar, Back / Next, sidebar, and when errors are shown.

What this file is for:
    The app shows one step at a time (one per section of parameters.yaml, then "Check and
    review"). This module keeps track of the step, draws the step heading, the progress bar
    (answered required questions), the Back / Next buttons and the sidebar with the status of
    every step, and decides which errors are shown now (visible_errors).

How the answers survive a change of step:
    Streamlit forgets the value of an input element that is not drawn, and only one step is
    drawn at a time. set_up_state() therefore hands every answer back to Streamlit at the start
    of each run (st.session_state[key] = st.session_state[key]), which makes Streamlit keep it.
    Tables cannot be kept like this; their cleaned rows are stored in st.session_state["tables"]
    (see questions.py) and the table is drawn again from there when the user comes back.
"""

import streamlit as st  # the web user interface

from checks import is_empty  # the definition of "not answered" (None, "", [])
from ui.common import EMPTY_ANSWERS, PROTOTYPE_NOTE, REVIEW_TITLE, section_of, step_title  # shared helpers


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
