"""ui - the parts of the Streamlit user interface; app.py is the entry point.

What this package is for:
    The user interface is split into small modules, one per part of the page, so that each
    file stays short and has one job. None of them contains rule logic (AI_PROMPT section 6):
    checks, clause choices and texts come from engine.py, the Word file from generator.py.

The modules:
    common.py            constants and small helpers used by several modules
    citations.py         the legal basis lines (articles with links, court decisions)
    navigation.py        steps, progress bar, Back / Next, sidebar, and when errors are shown
    questions.py         the questions of a step, the tables (milestones, annexes), the messages
    review.py            the last step: problems per step, summary, download, review screen
    contract_preview.py  the annotated contract (the Word contract shown like a sheet of paper)
    legal_sources.py     the "Legal sources" tab and the Fedlex check (uses law_check.py)
    style.css            small changes to Streamlit's look (sidebar, summary cards, contract)
"""
