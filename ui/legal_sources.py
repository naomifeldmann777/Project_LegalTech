"""ui/legal_sources.py - the "Legal sources" tab and the Fedlex check on the review screen.

What this file is for:
    It lists every legal source the contract relies on (clauses and warnings), with its
    summary, links and where it is used. "Check on Fedlex" adds the official text of each
    cited article and whether it still reads the same today as in the version the contract is
    based on (law_check.py); a demo switch simulates a change in the law. The Fedlex texts are
    kept for a day (st.cache_data), so the check is fast after the first time.
"""

from datetime import date  # today, and the demo's simulated day

import streamlit as st  # the web user interface

from law_check import FedlexError, check_citations, download  # the check of the cited articles on Fedlex
from ui.citations import citation_line  # summary and links of a source

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


@st.cache_data(ttl=ONE_DAY, show_spinner=False)  # each Fedlex address is loaded at most once a day
def fetch_from_fedlex(url):
    """Return the bytes at a Fedlex address (kept for a day, so the check is fast after the first time)."""
    return download(url)  # law_check.download raises FedlexError without a connection


@st.cache_data(ttl=ONE_DAY, show_spinner=False)  # the same citations on the same day: the same result
def run_law_check(citation_ids, today, _knowledge):
    """Return the Fedlex check of these citations (law_check.check_citations), kept for a day.

    _knowledge starts with "_", so Streamlit leaves it out of the cache key (it is always the same).
    """
    return check_citations(list(citation_ids), _knowledge, today, fetch=fetch_from_fedlex)  # the check


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
                report = run_law_check(tuple(used), DEMO_TODAY if demo else date.today(), knowledge)  # kept a day
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
