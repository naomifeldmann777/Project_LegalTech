"""law_check.py - checks on Fedlex whether the articles a contract cites still read the same today.

What this file is for:
    The review screen ("Legal sources" tab in app.py) lists every legal source the contract
    relies on. On request, this module loads the official German text of each cited article
    from Fedlex (the Swiss federal law database) in two versions and compares them:
      - the version the project's legal basis refers to (sources.yaml "law_version", e.g. 2026-10-01)
      - the version in force today
    The result per citation:
        unchanged      the cited text is the same in both versions
        changed        the cited text differs (the clauses based on it should be reviewed)
        missing        the article or paragraph is not in today's version (e.g. repealed)
        not_checkable  a court decision; Fedlex holds only statutes

How it works:
    1. sources.yaml links each statute to Fedlex; the link contains the law's ID (its "ELI"),
       e.g. eli/cc/27/317_321_377 for the Code of Obligations (SR 220).
    2. One query to Fedlex's public database (SPARQL) lists every version of that law with the
       date from which it applies and the address of its German XML file.
    3. The XML file marks every article (<article eId="art_374">) and paragraph
       (<paragraph eId="art_374/para_1">). Footnotes (<authorialNote>) are left out, so a new
       footnote alone does not count as a change.

How it fits into the project:
    No answers and no personal data are sent: only the law's ID and the file addresses.
    All network access goes through one function ("fetch"), so app.py can cache it and the
    tests can replace it with fixed example data (tests/test_law_check.py runs without internet).
    Only the Python standard library is used (urllib, json, xml).
"""

from datetime import date  # version dates and "today"
import json  # Fedlex answers the query in JSON
import re  # finds the law's ID in a link; reads article numbers such as "40a"
from urllib.parse import urlencode  # puts the query into the address
from urllib.request import Request, urlopen  # loads an address from the internet
import xml.etree.ElementTree as ElementTree  # reads the law's XML file


SPARQL_URL = "https://fedlex.data.admin.ch/sparqlendpoint"  # Fedlex's public database
FEDLEX_DATA = "https://fedlex.data.admin.ch/"  # start of every law ID in that database
GERMAN = "http://publications.europa.eu/resource/authority/language/DEU"  # language code of the German text
ELI_PATTERN = re.compile(r"eli/cc/[^/]+/[^/#?]+")  # e.g. "eli/cc/27/317_321_377" inside a Fedlex link
TIMEOUT_SECONDS = 30  # give up on Fedlex after 30 seconds
USER_AGENT = "construction-contract-generator (academic prototype)"  # generic client name, no personal data

# every version of one law (ACT_ELI is replaced) with its start date and the address of its German XML file
VERSIONS_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?date ?file WHERE {
  ?version jolux:isMemberOf <ACT_ELI> ;
           jolux:dateApplicability ?date ;
           jolux:isRealizedBy ?expression .
  ?expression jolux:language <GERMAN> ;
              jolux:isEmbodiedBy ?manifestation .
  ?manifestation jolux:isExemplifiedBy ?file .
  FILTER(CONTAINS(STR(?file), "/xml/"))
}
"""


class FedlexError(Exception):
    """Fedlex could not be reached, or it sent something this module cannot read."""


# ---------------------------------------------------------------------------
# Loading from Fedlex
# ---------------------------------------------------------------------------

def download(url):
    """Return the bytes at an internet address; raise FedlexError if that fails (no connection, timeout, ...)."""
    request = Request(url, headers={"Accept": "application/sparql-results+json, */*;q=0.1",  # JSON for the query
                                    "User-Agent": USER_AGENT})  # files are sent as they are
    try:  # the internet may not be reachable
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # open the address
            return response.read()  # all its bytes
    except OSError as error:  # no connection, timeout, HTTP error (all are OSError)
        raise FedlexError(f"could not load {url}: {error}") from error  # one clear error type for app.py


def act_eli(source):
    """Return the Fedlex ID of the statute a source links to, or None (e.g. for court decisions).

    Example: S1 (a link containing "eli/cc/27/317_321_377/...") -> "https://fedlex.data.admin.ch/eli/cc/27/317_321_377"
    """
    for key in ("url_statutory_text", "url"):  # S4 keeps the statute in url_statutory_text, S1 in url
        match = ELI_PATTERN.search(source.get(key) or "")  # look for "eli/cc/..." in the link
        if match:  # found
            return FEDLEX_DATA + match.group(0)  # the law's ID in Fedlex's database
    return None  # not a Fedlex statute


def versions(eli, fetch):
    """Return [(start date, address of the German XML file), ...] of every version of a law, oldest first."""
    query = VERSIONS_QUERY.replace("ACT_ELI", eli).replace("GERMAN", GERMAN)  # the query for this law
    url = SPARQL_URL + "?" + urlencode({"query": query})  # the query as an address
    try:  # the answer may not be what we expect
        rows = json.loads(fetch(url))["results"]["bindings"]  # one row per version (and file)
        found = {date.fromisoformat(row["date"]["value"]): row["file"]["value"] for row in rows}  # date -> file
    except (ValueError, KeyError) as error:  # not JSON, or other fields
        raise FedlexError(f"unexpected answer from Fedlex for {eli}") from error  # say so
    if not found:  # Fedlex knows no version of this law
        raise FedlexError(f"Fedlex lists no version of {eli}")  # say so
    return sorted(found.items())  # oldest first


def version_on(all_versions, day):
    """Return (start date, file) of the version that applies on a day: the latest one starting on or before it."""
    applicable = [version for version in all_versions if version[0] <= day]  # versions already in force on that day
    if not applicable:  # the law did not exist yet
        raise FedlexError(f"no version applies on {day}")  # say so
    return applicable[-1]  # the newest of them


# ---------------------------------------------------------------------------
# Reading the XML file
# ---------------------------------------------------------------------------

def read_articles(xml_bytes):
    """Return every article of a law's XML file: {eId: {"heading": "Art. 374", "lines": [(number, text), ...]}}.

    "lines" has one entry per paragraph: its number ("1", "1bis", or None for an unnumbered one)
    and its text, starting with the number, e.g. ("2", "2 Lässt sich während ...").
    """
    try:  # the file may be damaged
        root = ElementTree.fromstring(xml_bytes)  # the whole document
    except ElementTree.ParseError as error:  # not readable XML
        raise FedlexError("the law text from Fedlex could not be read") from error  # say so
    return {element.get("eId"): _article(element)  # each article under its ID, e.g. "art_374"
            for element in root.iter() if _local(element.tag) == "article"}  # all articles, however deep


def _article(element):
    """Return the heading and the paragraph lines of one <article> element."""
    heading = ""  # e.g. "Art. 374"
    lines = []  # the paragraphs
    for child in element:  # the parts of the article, in order
        name = _local(child.tag)  # e.g. "num" or "paragraph"
        text = _clean(_plain_text(child))  # its text without footnotes
        if name == "num":  # the article number
            heading = text  # e.g. "Art. 40a"
        elif name == "paragraph":  # one paragraph
            number = child.find("{*}num")  # its number, if it has one
            lines.append((_clean(_plain_text(number)) if number is not None else None, text))  # e.g. ("2", "2 ...")
        elif text:  # other text, e.g. "Aufgehoben" of a repealed article
            lines.append((None, text))  # keep it
    return {"heading": heading, "lines": lines}  # the article


def _plain_text(element):
    """Return all text inside an element, leaving out footnotes (<authorialNote>)."""
    parts = [element.text or ""]  # text before the first child
    for child in element:  # each child, in order
        if _local(child.tag) != "authorialNote":  # not a footnote
            parts.append(_plain_text(child))  # its text
        parts.append(child.tail or "")  # text after the child (also after a footnote)
    return "".join(parts)  # everything together


def _local(tag):
    """Return a tag name without its namespace, e.g. "{http://...akn/3.0}article" -> "article"."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""  # comments have no text tag


def _clean(text):
    """Return text with single spaces only (line breaks and indentation in the XML file removed)."""
    return " ".join(text.split())  # "  Ist der\n Preis " -> "Ist der Preis"


# ---------------------------------------------------------------------------
# The cited text of one citation
# ---------------------------------------------------------------------------

def cited_text(articles, citation):
    """Return the text a citation refers to (its article(s), or only its paragraphs), or None if it is missing.

    Examples: article "374" -> "Art. 374\\nIst der Preis ..."; article "366", paragraph "2" -> "Art. 366\\n2 Lässt ..."
    """
    texts = []  # one text per article
    for number in _article_numbers(citation["article"]):  # e.g. ["107", "108"] for "107-108"
        article = articles.get(_article_id(number))  # the article in the XML file
        if article is None:  # not in this version
            return None  # missing
        lines = _cited_lines(article["lines"], citation.get("paragraph"))  # the cited paragraphs
        if lines is None:  # a cited paragraph is not in this version
            return None  # missing
        texts.append("\n".join([article["heading"]] + lines))  # heading, then the paragraphs
    return "\n\n".join(texts)  # the articles, separated by an empty line


def _article_numbers(spec):
    """Return the article numbers of a citation: "107-109" -> ["107", "108", "109"], "40a" -> ["40a"]."""
    match = re.fullmatch(r"(\d+)-(\d+)", spec)  # a range of plain numbers?
    if match:  # yes
        return [str(number) for number in range(int(match.group(1)), int(match.group(2)) + 1)]  # every number
    return [spec]  # one article


def _article_id(number):
    """Return the XML ID of an article number: "374" -> "art_374", "40a" -> "art_40_a"."""
    match = re.fullmatch(r"(\d+)([a-z]*)", number)  # digits, then maybe letters
    if match is None:  # an unusual number
        return f"art_{number}"  # best guess
    digits, letters = match.groups()  # e.g. "40", "a"
    return f"art_{digits}" + (f"_{letters}" if letters else "")  # e.g. "art_40_a"


def _cited_lines(lines, paragraph):
    """Return the lines of the cited paragraphs ("2" or a range "1-3"); all lines if no paragraph is given."""
    if paragraph is None:  # the whole article
        return [text for _, text in lines]  # every line
    numbered = [(number, text) for number, text in lines if number]  # paragraphs with a number
    if not numbered:  # the article has a single unnumbered paragraph
        return [text for _, text in lines]  # the whole text
    match = re.fullmatch(r"(\d+)-(\d+)", paragraph)  # a range?
    if match:  # e.g. "1-3": also "1bis" belongs to it
        low, high = int(match.group(1)), int(match.group(2))  # the limits
        chosen = [text for number, text in numbered if low <= _number_part(number) <= high]  # inside the range
    else:  # one paragraph, e.g. "2"
        chosen = [text for number, text in numbered if number == paragraph]  # exactly that one
    return chosen or None  # None if the cited paragraph does not exist


def _number_part(number):
    """Return the leading number of a paragraph number: "1bis" -> 1 (0 if there is none)."""
    match = re.match(r"\d+", number)  # the digits at the start
    return int(match.group(0)) if match else 0  # e.g. 1


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def check_citations(citation_ids, knowledge, today, fetch=download):
    """Return the check of every citation: {citation_id: {status, our_text, today_text, our_version, today_version}}.

    our_version / today_version are the start dates of the two versions compared; for a court
    decision every value except the status is None. fetch(url) -> bytes loads an address
    (download by default; app.py passes a cached version, the tests fixed example data).
    today is normally the real date; the app's demo passes another day to simulate a change in the law.
    """
    basis_day = date.fromisoformat(str(knowledge["law_version"]))  # the legal basis of the project, e.g. 2026-10-01
    laws = {}  # source ID -> the two versions of that law, loaded once
    report = {}  # the result, filled below
    for citation_id in citation_ids:  # each citation of the contract
        citation = knowledge["citations"][citation_id]  # from sources.yaml
        eli = act_eli(knowledge["sources"][citation["source"]])  # the law on Fedlex, or None
        if eli is None or citation.get("url"):  # a court decision (it has its own link) or no Fedlex law
            report[citation_id] = {"status": "not_checkable", "our_text": None, "today_text": None,
                                   "our_version": None, "today_version": None}  # nothing to compare
            continue  # next citation
        if citation["source"] not in laws:  # this law is not loaded yet
            laws[citation["source"]] = _load_law(eli, basis_day, today, fetch)  # both versions
        law = laws[citation["source"]]  # the two versions
        our_text = cited_text(law["our_articles"], citation)  # the text the project is based on
        today_text = cited_text(law["today_articles"], citation)  # the text in force today
        report[citation_id] = {"status": _status(our_text, today_text), "our_text": our_text, "today_text": today_text,
                               "our_version": law["our_version"], "today_version": law["today_version"]}  # result
    return report  # e.g. {"CO_374": {"status": "unchanged", ...}}


def _load_law(eli, basis_day, today, fetch):
    """Load the version of a law the project is based on and the version in force today (once if they are the same)."""
    all_versions = versions(eli, fetch)  # every version with its date and file
    our_date, our_file = version_on(all_versions, basis_day)  # in force on the legal basis date
    today_date, today_file = version_on(all_versions, today)  # in force today (later versions are ignored)
    our_articles = read_articles(fetch(our_file))  # the articles of our version
    same = today_file == our_file  # no newer version in force yet
    today_articles = our_articles if same else read_articles(fetch(today_file))  # load the second file only if needed
    return {"our_version": our_date, "today_version": today_date,  # the dates
            "our_articles": our_articles, "today_articles": today_articles}  # the articles


def _status(our_text, today_text):
    """Return "unchanged", "changed" or "missing" for the two texts of one citation."""
    if our_text is None or today_text is None:  # not found in one of the versions
        return "missing"  # e.g. repealed
    return "unchanged" if our_text == today_text else "changed"  # compare word for word
