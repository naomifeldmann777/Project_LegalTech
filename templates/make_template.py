"""make_template.py - builds the Word template templates/contract_template.docx.

What this file is for:
    It rebuilds the law student's contract skeleton (Construction_Contract_Skeleton_EN)
    word for word as a Word file with gaps for docxtpl, and lays it out like a real
    contract: A4 pages, a serif font, a title block, the parties side by side in shaded
    boxes, numbered section headings with a fine line, justified clause text, the
    signatures side by side, and a header and footer with page numbers.
    The gaps use double braces, e.g. {{ client_name }} or {{ price_clause }};
    generator.py fills them. Lines like {%p if has_annexes %} are docxtpl control
    lines: they choose between two versions of a paragraph and disappear from the
    finished contract.

How it fits into the project:
    Run it once after every change to the skeleton wording or the layout:
        python templates/make_template.py
    It overwrites templates/contract_template.docx. The legal wording of the fixed
    parts lives here; the clause texts live in data/clauses.yaml. The layout only
    changes how the text looks, never its wording.

Which documents it implements:
    - Contract skeleton (sections 1-13), copied word for word
    - Law packet Task 12 (title "Construction Contract"), Task 13 (prototype note
      below the title and in the footer), consistency c (comma in the section 7 heading)
    - Law colleague's answers 2 (texts of sections 2, 3 and 13 when there are no
      annexes) and 3 (section 11 text while section 7 had no defect notice contact;
      kept, because the original skeleton text of section 11 is not in this repository)
    - Decisions D30 (one slot per clause group), D33 (all 13 sections stay)

Gaps that generator.py must fill:
    contract_date, client_name, client_address, contractor_name, contractor_address,
    site_address, work_description, exclusions_and_client_supplies, annex_register,
    has_annexes (true / false), price_clause, payment_clause, deadline_clause,
    penalty_clause, acceptance_clause, defects_clause, liability_clause,
    termination_clause, contractor_signatory_name, contractor_signatory_capacity
    (deadline_clause and penalty_clause may stay empty: no binding date, no penalty; their
    paragraph is then left out with {%p if ... %}, so no empty line remains in section 6;
    without a binding date, section 6 says that no date and no penalty were agreed)
"""

from pathlib import Path  # builds the file path next to this script

from docx import Document  # python-docx: creates Word files
from docx.enum.table import WD_TABLE_ALIGNMENT  # centres the tables on the page
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT  # paragraph alignment and tab stops
from docx.oxml import OxmlElement  # builds Word XML elements that python-docx has no function for
from docx.oxml.ns import qn  # turns a short name like "w:shd" into Word's full XML name
from docx.shared import Mm, Pt, RGBColor  # sizes in millimetres and points; colours


TEMPLATE_PATH = Path(__file__).parent / "contract_template.docx"  # where the template is saved

# footer on every page (law packet Task 13)
FOOTER_TEXT = "Academic prototype - not for signature"

# ---------------------------------------------------------------------------
# Layout: page, font and colours (only the look, never the wording)
# ---------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = Mm(210), Mm(297)  # A4, the paper size used in Switzerland
SIDE_MARGIN = Mm(25)  # 2.5 cm left and right
TEXT_WIDTH = PAGE_WIDTH - 2 * SIDE_MARGIN  # 16 cm of text between the margins

FONT = "Georgia"  # a classic serif font for contracts; installed on Windows and macOS
BODY_SIZE = Pt(10.5)  # size of the normal text
SMALL_SIZE = Pt(8)  # size of the header and footer

TEXT_COLOR = RGBColor(0x1A, 0x1A, 0x1A)  # almost black, as in the app
NAVY = RGBColor(0x1F, 0x4E, 0x79)  # dark blue for the title and the headings (the app's primary colour)
GREY = RGBColor(0x59, 0x59, 0x59)  # grey for secondary text (subtitle, header, footer)

NAVY_HEX = "1F4E79"  # the same dark blue, written as Word's XML expects it
RULE_HEX = "B7C7D9"  # light blue-grey for the fine lines under the headings
GREY_HEX = "595959"  # the same grey as GREY, for the page numbers
BOX_FILL = "EEF3F8"  # light blue-grey background of the parties boxes
NOTE_FILL = "F7F5F0"  # warm off-white background of the prototype note (the app's background colour)

# Word reads the properties of a paragraph (w:pPr) and of a run of text (w:rPr) in a
# fixed order. A new element must be placed before every element that comes after it
# in that order, otherwise Word may refuse to open the file. These lists are the
# elements that come after a border, a shading and a letter spacing.
AFTER_BORDER = ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
                "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid",
                "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
                "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId",
                "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")  # everything after w:pBdr
AFTER_SHADING = AFTER_BORDER[1:]  # everything after w:shd
AFTER_LETTER_SPACING = ("w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect",
                        "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang",
                        "w:eastAsianLayout", "w:specVanish", "w:oMath")  # everything after w:spacing in w:rPr


# ---------------------------------------------------------------------------
# Small helpers for Word's XML (lines, background colours, letter spacing)
# ---------------------------------------------------------------------------

def add_border(properties, side, color, size, space):
    """Add a line on one side ("top", "left", "bottom" or "right") of a paragraph or paragraph style.

    properties: the w:pPr element of the paragraph or style
    size: thickness in eighths of a point (8 = 1 pt); space: gap to the text in points
    Sides must be added in the order top, left, bottom, right (Word's order).
    """
    borders = properties.find(qn("w:pBdr"))  # the borders that are already there, if any
    if borders is None:  # no border yet
        borders = OxmlElement("w:pBdr")  # a new group of borders
        properties.insert_element_before(borders, *AFTER_BORDER)  # at the place Word expects it
    line = OxmlElement(f"w:{side}")  # one line, e.g. <w:bottom>
    line.set(qn("w:val"), "single")  # a plain single line
    line.set(qn("w:sz"), str(size))  # its thickness
    line.set(qn("w:space"), str(space))  # the gap between text and line
    line.set(qn("w:color"), color)  # its colour
    borders.append(line)  # add it to the group


def add_shading(properties, fill):
    """Give a paragraph or paragraph style a background colour (properties: its w:pPr element)."""
    shading = OxmlElement("w:shd")  # a background
    shading.set(qn("w:val"), "clear")  # a plain colour without a pattern
    shading.set(qn("w:color"), "auto")  # no pattern colour
    shading.set(qn("w:fill"), fill)  # the background colour
    properties.insert_element_before(shading, *AFTER_SHADING)  # at the place Word expects it


def shade_cell(cell, fill):
    """Give a table cell a background colour."""
    properties = cell._tc.get_or_add_tcPr()  # the cell's properties (python-docx has no function for shading)
    shading = OxmlElement("w:shd")  # a background
    shading.set(qn("w:val"), "clear")  # a plain colour without a pattern
    shading.set(qn("w:color"), "auto")  # no pattern colour
    shading.set(qn("w:fill"), fill)  # the background colour
    properties.append(shading)  # after the cell width, as Word expects


def set_letter_spacing(run_properties, points):
    """Spread the letters of a run or style apart (run_properties: its w:rPr element)."""
    spacing = OxmlElement("w:spacing")  # letter spacing
    spacing.set(qn("w:val"), str(int(points * 20)))  # Word counts in twentieths of a point
    run_properties.insert_element_before(spacing, *AFTER_LETTER_SPACING)  # at the place Word expects it


def set_style_font(style, size, color, bold=False, italic=False):
    """Give a style the contract font, a size, a colour and bold or italics; Word's theme fonts are removed."""
    style.font.name = FONT  # the font for normal letters
    fonts = style.element.rPr.rFonts  # the font settings in Word's XML
    for attribute in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):  # theme fonts would win over FONT
        fonts.attrib.pop(qn(attribute), None)  # so remove them
    fonts.set(qn("w:eastAsia"), FONT)  # also for other scripts, so Word never falls back to another font
    style.font.size = size  # the size in points
    style.font.color.rgb = color  # the colour
    style.font.bold = bold  # bold on or off
    style.font.italic = italic  # italics on or off


def add_field(paragraph, instruction):
    """Add a Word field such as PAGE (the current page) or NUMPAGES (the number of pages) to a paragraph."""
    field = OxmlElement("w:fldSimple")  # a simple field; Word fills in the number when it shows the page
    field.set(qn("w:instr"), instruction)  # which number
    run = OxmlElement("w:r")  # the text shown until Word updates the field
    properties = OxmlElement("w:rPr")  # its look
    color = OxmlElement("w:color")  # grey, like the rest of the footer
    color.set(qn("w:val"), GREY_HEX)  # the grey
    size = OxmlElement("w:sz")  # the size, in half points
    size.set(qn("w:val"), str(int(SMALL_SIZE.pt * 2)))  # 8 pt = 16 half points
    properties.append(color)  # colour first (Word's order) ...
    properties.append(size)  # ... then the size
    run.append(properties)  # the look of the run
    text = OxmlElement("w:t")  # the placeholder text
    text.text = "1"  # replaced by the real number in Word
    run.append(text)  # the text of the run
    field.append(run)  # the run inside the field
    paragraph._p.append(field)  # the field at the end of the paragraph


# ---------------------------------------------------------------------------
# Page, styles, header and footer
# ---------------------------------------------------------------------------

def set_up_page(doc):
    """A4 pages with 2.5 cm margins; the first page has no header (the title is there)."""
    section = doc.sections[0]  # the document has one section
    section.page_width, section.page_height = PAGE_WIDTH, PAGE_HEIGHT  # A4 instead of python-docx's US Letter
    section.left_margin = section.right_margin = SIDE_MARGIN  # 2.5 cm left and right
    section.top_margin, section.bottom_margin = Mm(25), Mm(22)  # top and bottom
    section.header_distance = section.footer_distance = Mm(12)  # header and footer close to the edge
    section.different_first_page_header_footer = True  # page 1 gets its own (empty) header


def set_up_styles(doc):
    """Set the look of the normal text, the title and the two heading levels."""
    normal = doc.styles["Normal"]  # the style of every normal paragraph
    set_style_font(normal, BODY_SIZE, TEXT_COLOR)  # Georgia, 10.5 pt, almost black
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # justified, like a printed contract
    normal.paragraph_format.space_before = Pt(0)  # no space above a paragraph ...
    normal.paragraph_format.space_after = Pt(6)  # ... and a little below it
    normal.paragraph_format.line_spacing = 1.2  # slightly more air between the lines
    normal.paragraph_format.widow_control = True  # no single line left alone at the top or bottom of a page

    title = doc.styles["Title"]  # "Construction Contract"
    set_style_font(title, Pt(24), NAVY)  # large and dark blue
    title.font.all_caps = True  # printed in capitals; the text itself stays "Construction Contract"
    set_letter_spacing(title.element.get_or_add_rPr(), 3)  # letters spread apart
    old_line = title.element.pPr.find(qn("w:pBdr"))  # python-docx's default blue line under the title
    if old_line is not None:  # it is there
        title.element.pPr.remove(old_line)  # remove it; the subtitle gets its own line
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER  # centred
    title.paragraph_format.space_before = Pt(18)  # some space at the top of the page
    title.paragraph_format.space_after = Pt(4)  # close to the subtitle

    part = doc.styles["Heading 1"]  # the two part headings ("Contract terms", "General provisions ...")
    set_style_font(part, Pt(10.5), NAVY, bold=True)  # dark blue, bold
    part.font.all_caps = True  # in capitals
    set_letter_spacing(part.element.get_or_add_rPr(), 2)  # letters spread apart
    part.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER  # centred
    part.paragraph_format.space_before = Pt(24)  # clear space above a new part
    part.paragraph_format.space_after = Pt(6)  # and a little below
    part.paragraph_format.keep_with_next = True  # never alone at the bottom of a page
    add_border(part.element.get_or_add_pPr(), "top", NAVY_HEX, 6, 6)  # a line above ...
    add_border(part.element.get_or_add_pPr(), "bottom", NAVY_HEX, 6, 6)  # ... and below the part heading

    section_heading = doc.styles["Heading 2"]  # the numbered sections ("1 Parties", ...)
    set_style_font(section_heading, Pt(11.5), NAVY, bold=True)  # dark blue, bold
    section_heading.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT  # left
    section_heading.paragraph_format.space_before = Pt(16)  # space above a new section
    section_heading.paragraph_format.space_after = Pt(6)  # a little below
    section_heading.paragraph_format.keep_with_next = True  # never alone at the bottom of a page
    add_border(section_heading.element.get_or_add_pPr(), "bottom", RULE_HEX, 4, 3)  # a fine line under it

    footer = doc.styles["Footer"]  # the style of the footer paragraph
    footer.paragraph_format.tab_stops.clear_all()  # remove python-docx's default tab stops (made for US Letter)
    footer.paragraph_format.tab_stops.add_tab_stop(TEXT_WIDTH, WD_TAB_ALIGNMENT.RIGHT)  # page numbers at the right edge
    footer.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT  # left


def keep_short_lines_unstretched(doc):
    """Stop Word from stretching a justified line that ends with a line break (e.g. the milestone rows)."""
    settings = doc.settings.element  # the document settings (settings.xml)
    compatibility = settings.find(qn("w:compat"))  # Word's compatibility options
    if compatibility is None:  # not there yet
        compatibility = OxmlElement("w:compat")  # create them
        settings.append(compatibility)  # add them to the settings
    option = OxmlElement("w:doNotExpandShiftReturn")  # "do not stretch lines that end with a line break"
    first_setting = compatibility.find(qn("w:compatSetting"))  # the newer options must stay at the end
    if first_setting is not None:  # there are newer options
        first_setting.addprevious(option)  # put the option before them (Word's order)
    else:  # no newer options
        compatibility.append(option)  # simply add it


def small_run(paragraph, text):
    """Add small grey text (header and footer) to a paragraph and return the run."""
    run = paragraph.add_run(text)  # the text
    run.font.size = SMALL_SIZE  # 8 pt
    run.font.color.rgb = GREY  # grey
    return run  # for further formatting


def fill_header(header):
    """Header of pages 2 and following: the contract title on the right, with a fine line."""
    paragraph = header.paragraphs[0]  # the header's empty paragraph
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT  # right
    run = small_run(paragraph, "Construction Contract")  # the title of the contract
    run.font.small_caps = True  # in small capitals
    set_letter_spacing(run._r.get_or_add_rPr(), 1)  # letters slightly apart
    add_border(paragraph._p.get_or_add_pPr(), "bottom", RULE_HEX, 4, 4)  # a fine line under the header


def fill_footer(footer):
    """Footer of every page: the prototype note (law packet Task 13) on the left, "Page x of y" on the right."""
    paragraph = footer.paragraphs[0]  # the footer's empty paragraph
    add_border(paragraph._p.get_or_add_pPr(), "top", RULE_HEX, 4, 4)  # a fine line above the footer
    small_run(paragraph, FOOTER_TEXT)  # law packet Task 13
    small_run(paragraph, "\tPage ")  # jump to the right edge
    add_field(paragraph, "PAGE")  # the current page number
    small_run(paragraph, " of ")  # "of"
    add_field(paragraph, "NUMPAGES")  # the number of pages


# ---------------------------------------------------------------------------
# Small helpers that add one piece of text to the document
# ---------------------------------------------------------------------------

def add_text(container, text, italic=False):
    """Add one paragraph with the given text (optionally in italics) and return it.

    container: the document or a table cell
    """
    paragraph = container.add_paragraph()  # a new, empty paragraph
    run = paragraph.add_run(text)  # the text as one piece ("run"), so a {{ gap }} is never split
    run.italic = italic  # italics on or off
    return paragraph  # for further formatting


def write_lines(paragraph, lines):
    """Write lines into a paragraph, separated by line breaks; labels such as "Client:" are printed in bold.

    A line ending with ":" and a line without ":" and without a gap (e.g. "Client") are labels.
    In "Label: value" only the label is bold; the value stays one run, so a {{ gap }} is never split.
    """
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT  # lists of details are not justified
    for number, line in enumerate(lines):  # each line, counted from 0
        if number > 0:  # every line except the first ...
            paragraph.add_run().add_break()  # ... starts on a new line
        if line.endswith(":") or (": " not in line and "{{" not in line):  # the whole line is a label
            paragraph.add_run(line).bold = True  # bold
        elif ": " in line:  # a label followed by a value
            label, value = line.split(": ", 1)  # e.g. "Address" and "{{ client_address }}"
            paragraph.add_run(label + ": ").bold = True  # the label in bold
            paragraph.add_run(value)  # the value
        else:  # only a value, e.g. "{{ work_description }}"
            paragraph.add_run(line)  # normal text


def add_lines(container, *lines):
    """Add one paragraph whose lines are separated by line breaks (see write_lines) and return it."""
    paragraph = container.add_paragraph()  # a new, empty paragraph
    write_lines(paragraph, lines)  # the lines
    return paragraph  # for further formatting


def add_control(doc, tag):
    """Add a docxtpl control line such as {%p if has_annexes %}; it is removed when the contract is generated."""
    doc.add_paragraph(tag)  # must stand alone in its own paragraph (docxtpl rule for "{%p ... %}")


def add_side_by_side_table(doc, rows):
    """Add a borderless table with two columns and a narrow gap between them, and return it.

    rows: the number of rows. Each row is never split across two pages.
    """
    table = doc.add_table(rows=rows, cols=3)  # left column, narrow gap, right column
    table.alignment = WD_TABLE_ALIGNMENT.CENTER  # centred on the page
    table.autofit = False  # keep the widths below
    widths = (Mm(77), Mm(6), Mm(77))  # together exactly the text width of 16 cm
    for row in table.rows:  # each row
        for cell, width in zip(row.cells, widths):  # each cell with its width
            cell.width = width  # the width of the cell
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))  # the row is never split across two pages
    for column, width in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths):  # the table's column grid
        column.set(qn("w:w"), str(int(width.twips)))  # the same widths, so every program uses them
    return table  # for filling


def add_party_boxes(doc, left_lines, right_lines):
    """Add the two parties side by side, each in a shaded box."""
    table = add_side_by_side_table(doc, 1)  # one row: Client box, gap, Contractor box
    for cell, lines in ((table.rows[0].cells[0], left_lines), (table.rows[0].cells[2], right_lines)):  # the two boxes
        shade_cell(cell, BOX_FILL)  # light blue-grey background
        paragraph = cell.paragraphs[0]  # the cell's first, empty paragraph
        write_lines(paragraph, lines)  # the lines of the box
        paragraph.paragraph_format.space_before = Pt(6)  # air above the text inside the box
        paragraph.paragraph_format.space_after = Pt(6)  # and below it


def add_signature_block(doc, rows):
    """Add the signatures side by side, one table row per line, so both columns line up.

    rows: (left text, right text) per row; None leaves a cell empty. A text ending with
    ":" (e.g. "Place and date:") gets room above it and a line under it to write on.
    """
    table = add_side_by_side_table(doc, len(rows))  # one row per line of the signature block
    for row, texts in zip(table.rows, rows):  # each row with its two texts
        for cell, text in zip((row.cells[0], row.cells[2]), texts):  # left and right column
            paragraph = cell.paragraphs[0]  # the cell's first, empty paragraph
            paragraph.paragraph_format.keep_with_next = True  # the whole block stays together on one page
            if text is None:  # nothing in this cell
                continue  # leave it empty
            write_lines(paragraph, [text])  # the text, with the label in bold
            if text.endswith(":"):  # a line to write on
                paragraph.paragraph_format.space_before = Pt(28)  # room to write by hand above the line
                add_border(paragraph._p.get_or_add_pPr(), "bottom", GREY_HEX, 6, 1)  # the line to write on


# ---------------------------------------------------------------------------
# The template, section by section
# ---------------------------------------------------------------------------

def build_template():
    """Build the template document and save it to templates/contract_template.docx."""
    doc = Document()  # a new, empty Word document
    set_up_page(doc)  # A4, margins
    set_up_styles(doc)  # font, title and headings
    keep_short_lines_unstretched(doc)  # justified lines ending with a line break stay normal

    # --- title block ---------------------------------------------------------
    doc.add_heading("Construction Contract", level=0)  # law packet Task 12 (skeleton said "iConstruction")
    subtitle = add_text(doc, "Contract for residential building works in Switzerland", italic=True)  # skeleton subtitle
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER  # centred under the title
    subtitle.runs[0].font.size = Pt(12)  # a bit larger than the text
    subtitle.runs[0].font.color.rgb = GREY  # grey
    subtitle.paragraph_format.space_after = Pt(14)  # space before the line
    add_border(subtitle._p.get_or_add_pPr(), "bottom", NAVY_HEX, 8, 10)  # a 1 pt dark blue line under the title block
    note = add_text(doc, "Academic prototype for seminar demonstration. This document may contain incomplete sections "
                         "and requires completion and legal review before use.", italic=True)  # law packet Task 13
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER  # centred
    note.runs[0].font.size = Pt(9)  # smaller than the text
    note.runs[0].font.color.rgb = GREY  # grey
    note.paragraph_format.left_indent = note.paragraph_format.right_indent = Mm(12)  # narrower than the text
    note.paragraph_format.space_before = Pt(12)  # space after the line
    note.paragraph_format.space_after = Pt(12)  # space before the date
    for side in ("top", "left", "bottom", "right"):  # a thin frame on all four sides (Word's order)
        add_border(note._p.get_or_add_pPr(), side, RULE_HEX, 4, 6)  # light blue-grey
    add_shading(note._p.get_or_add_pPr(), NOTE_FILL)  # warm off-white background
    date_line = add_lines(doc, "Contract date: {{ contract_date }}")  # skeleton; formatted like "1 November 2026"
    date_line.alignment = WD_ALIGN_PARAGRAPH.CENTER  # centred
    date_line.paragraph_format.space_after = Pt(10)  # space before section 1

    # --- 1 Parties -------------------------------------------------------------
    doc.add_heading("1 Parties", level=2)  # skeleton section 1
    add_party_boxes(doc, ["Client: {{ client_name }}", "Address: {{ client_address }}"],  # the Client
                    ["Contractor: {{ contractor_name }}", "Address: {{ contractor_address }}"])  # the Contractor
    parties = add_text(doc, "The Client and the Contractor are together referred to as the Parties.")  # skeleton
    parties.paragraph_format.space_before = Pt(8)  # space after the boxes

    # --- 2 Works and site ------------------------------------------------------
    doc.add_heading("2 Works and site", level=2)  # skeleton section 2
    add_control(doc, "{%p if has_annexes %}")  # version with technical annexes
    add_text(doc, "The Contractor shall produce and deliver the result described below and in the listed technical "
                  "annexes (the Works). The Client shall pay the remuneration determined under section 5.")  # skeleton
    add_control(doc, "{%p else %}")  # version without annexes
    add_text(doc, "The Contractor shall produce and deliver the result described below (the Works). The Client shall "
                  "pay the remuneration determined under section 5.")  # law colleague's answer 2
    add_control(doc, "{%p endif %}")  # end of the two versions
    add_lines(doc, "Site address: {{ site_address }}")  # skeleton
    add_lines(doc, "Description of the Works and agreed result:", "{{ work_description }}")  # skeleton
    add_lines(doc, "Expressly excluded work and items supplied by the Client:",  # skeleton
              "{{ exclusions_and_client_supplies }}")  # empty answer -> text from parameters.yaml "if_empty_print"

    # --- 3 Contract documents --------------------------------------------------
    doc.add_heading("3 Contract documents", level=2)  # skeleton section 3
    add_control(doc, "{%p if has_annexes %}")  # version with technical annexes (skeleton)
    add_text(doc, "This Contract includes the technical annexes identified below by title, date and revision. "
                  "The Parties confirm that the listed annexes are available to both of them.")  # skeleton
    annexes = add_text(doc, "{{ annex_register }}")  # the list of annexes, one per line
    annexes.alignment = WD_ALIGN_PARAGRAPH.LEFT  # a list is not justified
    annexes.paragraph_format.left_indent = Mm(6)  # indented under the text
    add_text(doc, "SIA 118 and either Party's standard terms are not incorporated into this Contract. Technical "
                  "annexes describe the agreed Works; they are not used to introduce additional general legal "
                  "conditions. A discrepancy affecting the Works shall be raised promptly and resolved before the "
                  "affected work proceeds where practicable. Statutory rights remain reserved.")  # skeleton
    add_control(doc, "{%p else %}")  # version without annexes: the whole body is replaced (answer 2)
    add_text(doc, "No technical annexes are listed or incorporated into this Contract.")  # law colleague's answer 2
    add_text(doc, "SIA 118 and either Party’s standard terms are not incorporated into this Contract. Any "
                  "discrepancy affecting the description of the Works shall be raised promptly and resolved before "
                  "the affected work proceeds where practicable. Statutory rights remain reserved.")  # answer 2
    add_control(doc, "{%p endif %}")  # end of the two versions

    # --- 4 Definitions ---------------------------------------------------------
    doc.add_heading("4 Definitions", level=2)  # skeleton section 4
    add_text(doc, "Delivery means making the completed Works available to the Client as required by the Contract. "
                  "Inspection means examining the Works for conformity and defects. Acceptance and approval have "
                  "their respective effects under applicable Swiss law. A delivery record or inspection protocol "
                  "shall identify defects and reservations; these concepts are not interchangeable.")  # skeleton

    # --- Contract terms (sections 5-10) ----------------------------------------
    doc.add_heading("Contract terms", level=1)  # skeleton part heading
    doc.add_heading("5 Price and payment", level=2)  # skeleton section 5 (topic 1)
    add_text(doc, "{{ price_clause }}")  # slot: PRICE_FIXED or PRICE_ESTIMATE (clauses.yaml "slot")
    add_text(doc, "{{ payment_clause }}")  # slot: PAYMENT_ON_COMPLETION or PAYMENT_MILESTONE

    doc.add_heading("6 Completion date and delay penalty", level=2)  # topic 2
    add_control(doc, "{%p if deadline_clause %}")  # with a binding date
    add_text(doc, "{{ deadline_clause }}")  # slot: DEADLINE_FIXED
    add_control(doc, "{%p else %}")  # without a binding date (then there is no penalty either: R_PEN_01)
    # team draft, NOT YET APPROVED by the law student: only states what was not agreed, no legal consequence
    add_text(doc, "No binding completion date and no delay penalty have been agreed.")
    add_control(doc, "{%p endif %}")  # end of the condition
    add_control(doc, "{%p if penalty_clause %}")  # only with a delay penalty; otherwise the paragraph is left out
    add_text(doc, "{{ penalty_clause }}")  # slot: PENALTY_CAPPED or PENALTY_UNCAPPED
    add_control(doc, "{%p endif %}")  # end of the condition
    doc.add_heading("7 Inspection, acceptance and defects", level=2)  # topic 3; comma added (consistency c)
    add_text(doc, "{{ acceptance_clause }}")  # slot: ACCEPTANCE_PROTOCOL (always)
    add_text(doc, "{{ defects_clause }}")  # slot: DEFECTS_STANDARD (always)
    doc.add_heading("8 Liability", level=2)  # topic 4
    add_text(doc, "{{ liability_clause }}")  # slot: LIABILITY_LAW or LIABILITY_CAP
    doc.add_heading("9 Termination", level=2)  # topic 5
    add_text(doc, "{{ termination_clause }}")  # slot: TERMINATION_LAW or TERMINATION_FOR_CAUSE (clauses.yaml "slot")

    doc.add_heading("10 Changes to the Works", level=2)  # skeleton section 10 (PRICE_FIXED refers to it)
    add_text(doc, "The Parties shall record agreed changes to the Works and their effects on price and time in "
                  "writing before the changed work begins where practicable. A request or proposal does not itself "
                  "record agreement to a change. This procedure does not remove statutory duties to warn, statutory "
                  "relief or mandatory rights.")  # skeleton

    # --- General provisions and signatures (sections 11-13) --------------------
    doc.add_heading("General provisions and signatures", level=1)  # skeleton part heading
    doc.add_heading("11 Communications", level=2)  # skeleton section 11
    # whole body replaced by the law colleague's answer 3 (written while section 7 had no defect notice
    # contact); kept, because the original skeleton text is not in this repository (open point)
    add_text(doc, "Each Party shall promptly inform the other of changes to its contact details. Contract "
                  "communications may be sent to the relevant Party’s address stated in section 1 or to updated "
                  "contact details notified by that Party. Defect notices may be sent to the Contractor’s address "
                  "stated in section 1 or to updated defect-notice contact details notified by the Contractor. "
                  "Evidence of important communications should be kept. This section does not impose an additional "
                  "validity formality on a statutory notice; any applicable statutory form requirement remains "
                  "reserved.")  # answer 3

    doc.add_heading("12 Applicable law and disputes", level=2)  # skeleton section 12
    add_text(doc, "This Contract is governed by Swiss substantive law, including the applicable provisions on "
                  "contracts for work in the Swiss Code of Obligations.")  # skeleton, paragraph 1
    add_text(doc, "The Parties may first seek to resolve a dispute by direct discussion. Discussion is not a "
                  "condition for commencing proceedings or taking a step needed to preserve a right or "
                  "deadline.")  # skeleton, paragraph 2
    add_text(doc, "The courts having jurisdiction under applicable law shall have jurisdiction. No exclusive place "
                  "of jurisdiction or arbitration is agreed by this clause. Any mandatory jurisdiction and consumer "
                  "protections remain unaffected.")  # skeleton, paragraph 3

    doc.add_heading("13 Signatures", level=2)  # skeleton section 13
    add_control(doc, "{%p if has_annexes %}")  # version with technical annexes (skeleton)
    confirm_annexes = add_text(doc, "The Parties confirm that they have reviewed the completed Contract and the "
                                    "technical annexes identified in section 3.")  # skeleton
    confirm_annexes.paragraph_format.keep_with_next = True  # stays on the page of the signatures
    add_control(doc, "{%p else %}")  # version without annexes
    confirm = add_text(doc, "The Parties confirm that they have reviewed this Contract.")  # law colleague's answer 2
    confirm.paragraph_format.keep_with_next = True  # stays on the page of the signatures
    add_control(doc, "{%p endif %}")  # end of the two versions
    # the skeleton's underscore lines are drawn as real lines under "Place and date:" and "Signature:",
    # so they always fit the column exactly
    add_signature_block(doc, [  # one row per line; the Client has no "Capacity" line
        ("Client", "For the Contractor"),  # skeleton: the Client signs personally, someone signs for the company
        ("Name: {{ client_name }}", "Name: {{ contractor_signatory_name }}"),  # skeleton
        (None, "Capacity: {{ contractor_signatory_capacity }}"),  # e.g. "Managing director"
        ("Place and date:", "Place and date:"),  # skeleton: line to write on
        ("Signature:", "Signature:"),  # skeleton: line to sign on
    ])  # end of the signature block

    # --- header and footer -----------------------------------------------------
    section = doc.sections[0]  # the document has one section
    fill_header(section.header)  # pages 2 and following
    fill_footer(section.first_page_footer)  # page 1 (law packet Task 13: the note on every page)
    fill_footer(section.footer)  # pages 2 and following

    doc.save(TEMPLATE_PATH)  # write the Word file


if __name__ == "__main__":  # only runs when started directly: python templates/make_template.py
    build_template()  # build and save the template
    print(f"Template created: {TEMPLATE_PATH}")  # tell the user where it is
