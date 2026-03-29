# zotero_export.py — Standalone citation export for Collabora Online
#
# Installed in: /opt/collaboraoffice/share/Scripts/python/
# Called via CallPythonScript; no browser extension or Zotero desktop required.
#
# Phase 1 deliverable: proves the Python scripting pipeline end-to-end.
#
# Reads Zotero reference marks in the document (compatible with the native
# Zotero LibreOffice plugin) and exports the citation metadata as CSL-JSON,
# BibTeX, or RIS.

import json
import re


# ── Reference mark parsing (shared logic with zotero_fields.py) ──────────────

def _parse_rm(name):
    """Extract (code, fieldID) from a Zotero reference mark name.

    Name format: ZOTERO_<code> RND<13 alphanum>
    Returns (code, fid) or (None, None) if not a Zotero mark.
    """
    m = re.match(r'^ZOTERO_(.+)\s+RND([A-Za-z0-9]+)$', name)
    if m:
        return m.group(1), m.group(2)
    return None, None


# ── Citation parsing ──────────────────────────────────────────────────────────

def _parse_citation(code):
    """Extract citationItems from a Zotero CSL_CITATION field code string."""
    if not code:
        return []
    idx = code.find("{")
    if idx == -1:
        return []
    try:
        obj = json.loads(code[idx:])
        return obj.get("citationItems", [])
    except Exception:
        return []


def _uri_for_item(item):
    for key in ("uris", "uri"):
        v = item.get(key)
        if v and isinstance(v, list) and v[0]:
            return v[0]
    data = item.get("itemData", {})
    return data.get("id", "")


# ── Export formats ────────────────────────────────────────────────────────────

def _to_csljson(items):
    return json.dumps(items, ensure_ascii=False, indent=2)


def _escape_bib(s):
    """Escape special BibTeX characters in a string."""
    for ch in ("&", "%", "$", "#", "_", "{", "}", "~", "^", "\\"):
        s = s.replace(ch, "\\" + ch)
    return s


def _bibtex_authors(author_list):
    parts = []
    for a in author_list:
        if "family" in a:
            name = a["family"]
            if "given" in a:
                name += ", " + a["given"]
        elif "literal" in a:
            name = "{" + a["literal"] + "}"
        else:
            continue
        parts.append(name)
    return " and ".join(parts)


_TYPE_TO_BIBTEX = {
    "article-journal": "article",
    "article-magazine": "article",
    "article-newspaper": "article",
    "book": "book",
    "chapter": "incollection",
    "paper-conference": "inproceedings",
    "report": "techreport",
    "thesis": "phdthesis",
    "webpage": "misc",
    "dataset": "misc",
}


def _to_bibtex(items):
    lines = []
    for item in items:
        t = item.get("type", "misc")
        bib_type = _TYPE_TO_BIBTEX.get(t, "misc")
        key = re.sub(r"[^\w]", "", str(item.get("id", "ref")))

        fields = {}
        if "title" in item:
            fields["title"] = "{" + _escape_bib(item["title"]) + "}"
        if "author" in item:
            fields["author"] = _bibtex_authors(item["author"])
        if "editor" in item:
            fields["editor"] = _bibtex_authors(item["editor"])
        if "issued" in item:
            parts = item["issued"].get("date-parts", [[]])
            if parts and parts[0]:
                fields["year"] = str(parts[0][0])
        if "container-title" in item:
            key_name = "journal" if bib_type == "article" else "booktitle"
            fields[key_name] = "{" + _escape_bib(item["container-title"]) + "}"
        if "volume" in item:
            fields["volume"] = str(item["volume"])
        if "issue" in item:
            fields["number"] = str(item["issue"])
        if "page" in item:
            fields["pages"] = str(item["page"]).replace("-", "--")
        if "publisher" in item:
            fields["publisher"] = "{" + _escape_bib(item["publisher"]) + "}"
        if "publisher-place" in item:
            fields["address"] = "{" + _escape_bib(item["publisher-place"]) + "}"
        if "DOI" in item:
            fields["doi"] = item["DOI"]
        if "ISBN" in item:
            fields["isbn"] = item["ISBN"]
        if "URL" in item:
            fields["url"] = item["URL"]
        if "abstract" in item:
            fields["abstract"] = "{" + _escape_bib(item["abstract"]) + "}"

        lines.append(f"@{bib_type}{{{key},")
        lines.extend(f"  {k} = {{{v}}}," for k, v in fields.items())
        lines.append("}\n")

    return "\n".join(lines)


_TYPE_TO_RIS = {
    "article-journal": "JOUR",
    "article-magazine": "MGZN",
    "article-newspaper": "NEWS",
    "book": "BOOK",
    "chapter": "CHAP",
    "paper-conference": "CONF",
    "report": "RPRT",
    "thesis": "THES",
    "webpage": "ELEC",
    "dataset": "DATA",
}


def _to_ris(items):
    lines = []
    for item in items:
        t = item.get("type", "GEN")
        ris_type = _TYPE_TO_RIS.get(t, "GEN")
        lines.append(f"TY  - {ris_type}")
        if "title" in item:
            lines.append(f"TI  - {item['title']}")
        for a in item.get("author", []):
            name = a.get("family", "")
            if a.get("given"):
                name += ", " + a["given"]
            if name:
                lines.append(f"AU  - {name}")
        if "issued" in item:
            parts = item["issued"].get("date-parts", [[]])
            if parts and parts[0]:
                lines.append(f"PY  - {parts[0][0]}")
        if "container-title" in item:
            lines.append(f"JO  - {item['container-title']}")
        if "volume" in item:
            lines.append(f"VL  - {item['volume']}")
        if "issue" in item:
            lines.append(f"IS  - {item['issue']}")
        if "page" in item:
            lines.append(f"SP  - {item['page']}")
        if "publisher" in item:
            lines.append(f"PB  - {item['publisher']}")
        if "DOI" in item:
            lines.append(f"DO  - {item['DOI']}")
        if "URL" in item:
            lines.append(f"UR  - {item['URL']}")
        if "abstract" in item:
            lines.append(f"AB  - {item['abstract']}")
        lines.append("ER  -")
        lines.append("")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def exportCitations(format="csljson", **_):
    """Export all unique citations from the document.

    format: "csljson" | "bibtex" | "ris"
    Returns: JSON string containing the formatted bibliography.
    """
    doc = XSCRIPTCONTEXT.getDocument()  # noqa: F821
    rms = doc.getReferenceMarks()

    seen_uris = {}  # uri → itemData (deduplication)

    for name in rms.getElementNames():
        code, fid = _parse_rm(name)
        if not fid or not code:
            continue

        for ci in _parse_citation(code):
            item_data = ci.get("itemData")
            if not item_data:
                continue
            uri = _uri_for_item(ci)
            if uri not in seen_uris:
                seen_uris[uri] = item_data

    items = list(seen_uris.values())

    if format == "bibtex":
        return _to_bibtex(items)
    if format == "ris":
        return _to_ris(items)
    # _to_csljson already returns json.dumps(items); don't double-encode
    return _to_csljson(items)


def exportCitationsAsCSLJSON(**_):
    """Convenience wrapper — export as CSL-JSON."""
    return exportCitations(format="csljson")


def exportCitationsAsBibTeX(**_):
    """Convenience wrapper — export as BibTeX."""
    return exportCitations(format="bibtex")


def exportCitationsAsRIS(**_):
    """Convenience wrapper — export as RIS."""
    return exportCitations(format="ris")


# Required for the LibreOffice UNO runtime to discover these functions
g_exportedScripts = (
    exportCitations,
    exportCitationsAsCSLJSON,
    exportCitationsAsBibTeX,
    exportCitationsAsRIS,
)
