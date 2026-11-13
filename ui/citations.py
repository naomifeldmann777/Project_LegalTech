"""ui/citations.py - the legal basis lines shown next to messages, clauses and sources.

What this file is for:
    It turns citation IDs from sources.yaml into Markdown: the article with a link to the
    statute (and to the English translation), or a court decision with its explanation and
    "See court decision". The same look is used for errors, warnings, clauses and the
    "Legal sources" tab. Legal sources are shown in the app only, never in the contract
    (handoff App. C).
"""


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
