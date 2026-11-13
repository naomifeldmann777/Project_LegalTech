"""ui/review.py - the last step "Check and review": problems, summary, download and review screen.

What this file is for:
    With errors, it lists them per step with a "Go to this step" button and keeps the download
    disabled ("Generate" disabled while errors exist). Without errors, it shows the summary
    cards, the download button and the review screen in three tabs: the annotated contract
    (contract_preview.py), the clauses by topic with reason and legal basis, and the legal
    sources with the Fedlex check (legal_sources.py). Warnings are shown in both cases (D18).
"""

import streamlit as st  # the web user interface

from generator import GenerationError, generate_contract  # builds the Word file
from ui.citations import legal_basis, message_with_basis  # legal basis lines
from ui.common import section_of, step_title  # shared helpers
from ui.contract_preview import show_annotated_contract  # the "Annotated contract" tab
from ui.legal_sources import show_legal_sources  # the "Legal sources" tab
from ui.navigation import go_to  # "Go to this step"

WORD_FILE_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # file type of .docx


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
