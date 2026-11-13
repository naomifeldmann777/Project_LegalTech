"""tests/test_law_check.py - tests of the Fedlex check (law_check.py), without internet.

What this file is for:
    It checks that law_check.py finds the right law, the right version, the right article and
    paragraph, leaves out footnotes, and reports unchanged / changed / missing / not_checkable.
How it works:
    The real network access is replaced by fake_fetch(): it answers the version query with a
    fixed list of versions and each XML address with a small example law text, written in
    the same XML format as Fedlex (<article eId="art_374">, <paragraph>, <authorialNote>).
    The citations come from the real data/sources.yaml.
"""

from datetime import date  # version dates and "today"
import json  # the fake answer to the version query
from urllib.parse import unquote  # reads the query inside an address

import pytest  # the test framework

from data_loader import load_knowledge  # the real knowledge base (citations and sources)
from law_check import (FedlexError, act_eli, check_citations, cited_text, download, read_articles,  # module under test
                       SPARQL_URL, version_on)  # the address of the version query

TODAY = date(2026, 11, 13)  # a fixed "today", so the tests never depend on the real date
CO = "https://fedlex.data.admin.ch/eli/cc/27/317_321_377"  # the Code of Obligations on Fedlex
AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"  # the XML namespace Fedlex uses


def law_xml(art_163_para_3="Übermässig hohe Konventionalstrafen hat der Richter nach seinem Ermessen herabzusetzen.",
            with_art_374=True, footnote="AS 1911 317"):
    """Return a small example law in Fedlex's XML format; the arguments change one detail per version."""
    art_374 = ('<article eId="art_374"><num><b>Art. 374</b></num><paragraph eId="art_374/para"><content>'
               '<p>Ist der Preis zum voraus nicht bestimmt worden, so wird er festgesetzt.</p>'
               '</content></paragraph></article>') if with_art_374 else ""  # may be left out ("repealed")
    return (f'<akomaNtoso xmlns="{AKN}"><act><body><level eId="lvl_1">'  # articles sit deep inside levels
            f'{art_374}'
            '<article eId="art_163"><num><b>Art. 163</b></num>'
            '<paragraph eId="art_163/para_1"><num>1</num><content><p> Die Konventionalstrafe kann '
            f'in beliebiger Höhe bestimmt werden.<authorialNote><p>{footnote}</p></authorialNote></p></content></paragraph>'
            '<paragraph eId="art_163/para_3"><num>3</num><content><p> '
            f'{art_163_para_3}</p></content></paragraph></article>'
            '<article eId="art_40_a"><num><b>Art. 40</b><i>a</i></num><paragraph eId="art_40_a/para_1"><num>1</num>'
            '<content><p>Haustürgeschäfte.</p></content></paragraph></article>'
            '</level></body></act></akomaNtoso>').encode("utf-8")  # bytes, like a download


def fake_fetch(versions):
    """Return a fetch function: the version query lists `versions` ({date: xml}), each XML address returns its xml."""
    def fetch(url):  # replaces law_check.download
        if url.startswith(SPARQL_URL):  # the version query
            assert CO in unquote(url) or "1988/223_223_223" in unquote(url)  # only known laws are asked for
            rows = [{"date": {"value": day}, "file": {"value": f"https://example.test/{day}.xml"}} for day in versions]
            return json.dumps({"results": {"bindings": rows}}).encode("utf-8")  # the JSON answer
        return versions[url.rsplit("/", 1)[-1].removesuffix(".xml")]  # the XML of that version
    return fetch  # the fake


@pytest.fixture(scope="module")  # load the YAML files once for this file
def knowledge():
    """The real knowledge base from data/ (law_version 2026-10-01)."""
    return load_knowledge()  # read and check the four YAML files


# ---------------------------------------------------------------------------
# Finding the law, the version and the text
# ---------------------------------------------------------------------------

def test_the_law_is_found_in_the_source_links(knowledge):
    """S1 links to the Code of Obligations, S4 to the UWG; court decisions have no Fedlex law."""
    assert act_eli(knowledge["sources"]["S1"]) == CO  # from the PDF link of the CO
    assert act_eli(knowledge["sources"]["S4"]) == "https://fedlex.data.admin.ch/eli/cc/1988/223_223_223"  # UWG
    assert act_eli(knowledge["sources"]["BGER"]) is None  # the court's website


def test_the_version_in_force_on_a_day_is_the_latest_one_started():
    """Later versions are ignored: only the version already in force counts."""
    versions = [(date(2026, 1, 1), "a"), (date(2026, 10, 1), "b"), (date(2027, 7, 1), "c")]  # one in the future
    assert version_on(versions, TODAY) == (date(2026, 10, 1), "b")  # not the one from 2027
    with pytest.raises(FedlexError):  # before the first version
        version_on(versions, date(2025, 1, 1))  # no version applies


def test_articles_are_read_without_footnotes():
    """Heading, paragraph numbers and text are kept; the footnote is left out; "40a" becomes art_40_a."""
    articles = read_articles(law_xml())  # the example law
    assert articles["art_163"]["heading"] == "Art. 163"  # the article number
    assert articles["art_163"]["lines"][0] == ("1", "1 Die Konventionalstrafe kann in beliebiger Höhe bestimmt werden.")
    assert articles["art_40_a"]["heading"] == "Art. 40a"  # number and letter together


def test_only_the_cited_paragraph_is_returned():
    """A citation with a paragraph returns only that paragraph; without one the whole article."""
    articles = read_articles(law_xml())  # the example law
    text = cited_text(articles, {"article": "163", "paragraph": "3"})  # paragraph 3 only
    assert text == "Art. 163\n3 Übermässig hohe Konventionalstrafen hat der Richter nach seinem Ermessen herabzusetzen."
    assert cited_text(articles, {"article": "163", "paragraph": None}).count("\n") == 2  # heading + 2 paragraphs
    assert cited_text(articles, {"article": "163", "paragraph": "1-3"}).count("\n") == 2  # range: both paragraphs
    assert cited_text(articles, {"article": "163", "paragraph": "2"}) is None  # no paragraph 2 in the example
    assert cited_text(articles, {"article": "40a", "paragraph": None}).startswith("Art. 40a")  # letter article


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def test_same_version_today_means_unchanged(knowledge):
    """Only the version of 2026-10-01 is in force: every cited text is unchanged."""
    report = check_citations(["CO_374", "CO_163"], knowledge, TODAY, fake_fetch({"2026-10-01": law_xml()}))
    assert report["CO_374"]["status"] == "unchanged"  # the same text
    assert report["CO_374"]["today_text"].startswith("Art. 374\nIst der Preis")  # the official text is returned
    assert report["CO_163"]["our_version"] == report["CO_163"]["today_version"] == date(2026, 10, 1)  # one version


def test_a_changed_paragraph_is_reported_with_both_texts(knowledge):
    """A newer version in force today changes Art. 163 para. 3: changed, with the old and the new text."""
    fetch = fake_fetch({"2026-10-01": law_xml(),  # the legal basis of the project
                        "2026-11-01": law_xml(art_163_para_3="Übermässige Strafen werden herabgesetzt.")})  # today
    report = check_citations(["CO_374", "CO_163"], knowledge, TODAY, fetch)  # both citations
    assert report["CO_374"]["status"] == "unchanged"  # Art. 374 is the same
    assert report["CO_163"]["status"] == "changed"  # Art. 163 differs
    assert "nach seinem Ermessen" in report["CO_163"]["our_text"]  # the old text
    assert "werden herabgesetzt" in report["CO_163"]["today_text"]  # the new text
    assert report["CO_163"]["today_version"] == date(2026, 11, 1)  # compared with the version in force today


def test_a_future_version_is_ignored(knowledge):
    """A version that starts after today does not count, even if it changes the text."""
    fetch = fake_fetch({"2026-10-01": law_xml(),  # the legal basis and today
                        "2027-07-01": law_xml(art_163_para_3="Neu ab 2027.")})  # not yet in force
    assert check_citations(["CO_163"], knowledge, TODAY, fetch)["CO_163"]["status"] == "unchanged"  # still the same


def test_a_new_footnote_alone_is_not_a_change(knowledge):
    """Footnotes are left out, so a version that only adds a footnote leaves the text unchanged."""
    fetch = fake_fetch({"2026-10-01": law_xml(), "2026-11-01": law_xml(footnote="AS 2026 999")})  # other footnote
    assert check_citations(["CO_163"], knowledge, TODAY, fetch)["CO_163"]["status"] == "unchanged"  # same text


def test_a_repealed_article_is_missing(knowledge):
    """Art. 374 is not in today's version any more: missing, with the old text kept."""
    fetch = fake_fetch({"2026-10-01": law_xml(), "2026-11-01": law_xml(with_art_374=False)})  # 374 removed
    report = check_citations(["CO_374"], knowledge, TODAY, fetch)  # the check
    assert report["CO_374"]["status"] == "missing"  # not in force any more
    assert report["CO_374"]["our_text"].startswith("Art. 374")  # the old text is still shown


def test_a_simulated_today_compares_the_version_in_force_on_that_day(knowledge):
    """The app's demo passes another "today": the project's basis stays, the law in force is simulated."""
    fetch = fake_fetch({"2025-10-01": law_xml(art_163_para_3="Anderer Text."),  # another version
                        "2026-10-01": law_xml()})  # the project's basis, also in force on the real today
    assert check_citations(["CO_163"], knowledge, TODAY, fetch)["CO_163"]["status"] == "unchanged"  # normal case
    report = check_citations(["CO_163"], knowledge, date(2025, 10, 1), fetch)["CO_163"]  # the demo's "today"
    assert report["status"] == "changed"  # the simulated law differs
    assert report["our_version"] == date(2026, 10, 1) and report["today_version"] == date(2025, 10, 1)  # basis stays


def test_court_decisions_are_not_checkable(knowledge):
    """A court decision is not on Fedlex: not_checkable, and nothing is loaded for it."""
    def no_fetch(url):  # must not be called
        raise AssertionError(f"nothing should be loaded, but {url} was")  # fail the test
    report = check_citations(["BGE_114_II_264"], knowledge, TODAY, no_fetch)  # only a decision
    assert report["BGE_114_II_264"]["status"] == "not_checkable"  # cannot be checked


def test_no_connection_raises_fedlex_error():
    """Without a connection, download raises FedlexError (app.py shows a message instead of crashing)."""
    with pytest.raises(FedlexError):  # the one error type app.py catches
        download("http://127.0.0.1:9/")  # a local port where nothing answers (no internet needed)
