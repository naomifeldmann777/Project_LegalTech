"""app.py - the entry point of the Streamlit user interface of the Construction Contract Generator.

What this file is for:
    It draws one page of the app: the title, the progress bar, the current step (the questions
    of one section of parameters.yaml, or the last step "Check and review"), the Back / Next
    buttons and the sidebar. The parts of the page are in the ui package (see ui/__init__.py):
        ui/navigation.py        steps, progress bar, Back / Next, sidebar, when errors are shown
        ui/questions.py         the questions, the tables, the messages below the questions
        ui/review.py            the last step: problems, summary, download, review screen
        ui/contract_preview.py  the annotated contract ("Why ...?" for every chosen clause)
        ui/legal_sources.py     the legal sources and the Fedlex check (law_check.py)
        ui/citations.py         the legal basis lines; ui/common.py shared constants; ui/style.css
    The flow follows the process flowchart (diagrams PDF ch. 1):
        step 1 ... step 8 (questions) -> last step "Check and review"
            -> errors: listed per step; "Go to this step" leads back to the questions
            -> no errors: review screen -> download

How it fits into the project:
    Start it from the project root with:   streamlit run app.py
    The user interface only shows and collects; it contains no rule logic (AI_PROMPT section 6):
      - the questions and the steps come from data/parameters.yaml (via data_loader.py)
      - which questions are shown comes from "active_when" (engine.is_active)
      - all checks, clause choices and texts come from engine.evaluate()
      - the Word file comes from generator.generate_contract()
    The YAML files are loaded once; restart the app after changing a YAML file.
    The colours are set in .streamlit/config.toml, small changes to the look in ui/style.css.

Which documents it implements:
    AI_PROMPT step 17 (questionnaire with only active fields, milestones as a table,
    red errors next to the fields, yellow warnings, review screen, "Generate" disabled
    while errors exist, download button), diagrams PDF ch. 1 (user flow), handoff
    App. B (None = not answered: no answer is preselected), App. C (sources only on
    the review screen), law packet Task 13 (prototype note), decisions D18, D25, D28.
"""

from pathlib import Path  # the path of ui/style.css next to this file

import streamlit as st  # the web user interface

from data_loader import load_knowledge  # reads and checks the YAML files
from engine import evaluate  # the rule engine
from ui.common import PROTOTYPE_NOTE  # the prototype note (law packet Task 13)
from ui.navigation import (set_up_state, show_navigation, show_progress, show_sidebar,  # steps and sidebar
                           show_step_header, visible_errors)  # heading of a step; which errors are shown now
from ui.questions import ask_questions, show_messages  # the questions and the messages below them
from ui.review import show_check_step  # the last step "Check and review"

STYLE_FILE = Path(__file__).parent / "ui" / "style.css"  # small changes to Streamlit's look


@st.cache_resource  # load the YAML files only once, not on every click
def get_knowledge():
    """Return the knowledge base (all four YAML files, checked by data_loader.py)."""
    return load_knowledge()  # stops with a clear message if a YAML file has a mistake


def main():
    """Draw the page: progress, the current step (questions or "Check and review"), buttons and sidebar."""
    st.set_page_config(page_title="Construction Contract Generator", page_icon=":material/construction:")  # browser tab
    st.html(STYLE_FILE)  # the small style changes (a style-only block takes no space on the page)
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


main()  # Streamlit runs this file from top to bottom on every click
