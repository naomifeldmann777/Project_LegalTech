"""ui/contract_preview.py - the annotated contract on the review screen.

What this file is for:
    It shows the generated contract like a sheet of paper. Every clause chosen by the rules is
    highlighted and has a "Why ...?" button with the answers it is based on, the reason and the
    legal basis. The contract is read back from the same Word file the user downloads, so the
    preview always matches the download. The look is set in style.css.
"""

import html  # html.escape: contract text is written safely into the preview's HTML
from io import BytesIO  # read the generated Word file from memory

from docx import Document  # python-docx: reads the generated Word file back
from docx.enum.text import WD_ALIGN_PARAGRAPH  # to recognise centred paragraphs
from docx.table import Table  # a table in the Word file (parties, signatures)
import streamlit as st  # the web user interface

from checks import is_empty  # the definition of "not answered" (None, "", [])
from ui.citations import legal_basis  # legal basis lines
from ui.common import YES_NO  # how true / false answers are shown


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
