#!/usr/bin/env python3
"""
fix_html.py
Fixes indentation and renames UUID footnote IDs to short semantic IDs.

Semantic ID format: {DivSlug}-{H2Short}-{footnoteNumber}
  e.g.  Rules-section1-35   Rules-guidance1-2   Rules-schedule1-*

Dependencies: pip install beautifulsoup4
See process.md for full usage guide and adaptation instructions.
"""

import re
from pathlib import Path
from bs4 import BeautifulSoup, Tag, NavigableString, Doctype

# ── Configuration ─────────────────────────────────────────────────────────────

INPUT_PATH  = Path(r"c:\Users\Binura.Lakshan\Desktop\CUBE Scripts\asx_pdf_checker\output\8f4b0082-779f-11e9-ac50-64006a8e7d91\Updated_Books\result_.html")
OUTPUT_PATH = INPUT_PATH.parent / "result_formatted.html"

# UUID(s) in the document that are NOT footnotes and must not be renamed.
# Typically the document-level identifier that appears in <title>.
DOC_UUIDS = {'8f4b0082-779f-11e9-ac50-64006a8e7d91'}

# Organisation-specific prefix to strip before extracting H2 keyword.
# Change this regex if the document belongs to a different organisation.
_ORG_PREFIX = re.compile(r'asx\s+24\s*', re.IGNORECASE)

# Words that are too generic to serve as the section keyword.
_STOP_WORDS = {
    'of', 'to', 'the', 'and', 'a', 'an', 'in', 'for',
    'operating', 'rules', 'rule', 'note', 'its',
}

# ── Regex helpers ─────────────────────────────────────────────────────────────

UUID_RE   = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
UUID_SCAN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_SPEC_CHARS = re.compile(r'[–—:/()\.\*•,;!?@#$%^&+=<>|\\\"\']')
_LEAD_NL    = re.compile(r'^\s*\n\s*')
_TRAIL_NL   = re.compile(r'\s*\n\s*$')

# ── Serializer config ─────────────────────────────────────────────────────────

BLOCK_TAGS = {
    'html', 'head', 'body', 'div', 'p', 'table', 'thead', 'tbody', 'tfoot',
    'tr', 'th', 'td', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'meta', 'title', 'link', 'script', 'style', 'section', 'article', 'header',
    'footer', 'nav', 'main', 'aside', 'blockquote', 'figure', 'figcaption',
}
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
             'link', 'meta', 'param', 'source', 'track', 'wbr'}


# ── ID slug functions ─────────────────────────────────────────────────────────

def div_slug(sup_elem) -> str:
    """First alphabetic word of nearest ancestor <div> class, Title-cased."""
    parent = sup_elem.find_parent('div')
    if parent and parent.get('class'):
        cls = parent['class']
        cls = cls[0] if isinstance(cls, list) else str(cls)
        word = re.search(r'[a-zA-Z]+', cls)
        return word.group(0).capitalize() if word else 'Doc'
    return 'Doc'


def h2_short(text: str) -> str:
    """First meaningful keyword + first section number from an H2 heading, lowercase."""
    text = _SPEC_CHARS.sub(' ', text.strip())
    text = _ORG_PREFIX.sub(' ', text).strip()
    words = text.lower().split()
    keyword = next(
        (w for w in words if w not in _STOP_WORDS and not w.isdigit()),
        words[0] if words else 'unknown'
    )
    num_m = re.search(r'\b(\d+)\b', text)
    num   = num_m.group(1) if num_m else ''
    return keyword + num


# ── Build UUID → semantic-ID mapping ─────────────────────────────────────────

def build_mapping(soup) -> dict:
    """Walk DOM in document order; for each <sup> footnote ref, assign a short semantic ID."""
    mapping  = {}    # uuid → semantic_id
    used_ids = set()
    current_h2 = ''

    for elem in soup.find_all(True):
        name = elem.name
        if name == 'h2':
            current_h2 = h2_short(elem.get_text())
        elif name == 'sup':
            a_tag = elem.find('a')
            if not a_tag:
                continue
            href = a_tag.get('href', '')
            if not href.startswith('#'):
                continue
            uuid = href[1:]
            if not UUID_RE.match(uuid):
                continue
            if uuid in mapping:
                continue   # same footnote referenced more than once — already mapped
            number  = a_tag.get_text().strip()
            d_slug  = div_slug(elem)
            base    = f"{d_slug}-{current_h2 or 'preamble'}-{number}"
            # Resolve collisions (same base ID for two different UUIDs)
            semantic = base
            suffix   = 2
            while semantic in used_ids:
                semantic = f"{base}_{suffix}"
                suffix  += 1
            mapping[uuid] = semantic
            used_ids.add(semantic)

    # Any footnote <div id="UUID"> not yet in mapping gets a positional TABLE_NOTE id
    counter = 1
    for div in soup.find_all('div', class_='footnote'):
        uid = div.get('id', '')
        if UUID_RE.match(uid) and uid not in mapping:
            mapping[uid] = f"TABLE_NOTE_{counter}"
            counter += 1

    return mapping


# ── Custom HTML serializer ────────────────────────────────────────────────────

def attrs_str(tag: Tag) -> str:
    parts = []
    for k, v in tag.attrs.items():
        if isinstance(v, list):
            v = ' '.join(v)
        parts.append(f'{k}="{v}"')
    return (' ' + ' '.join(parts)) if parts else ''


def serialize_inline(node, out: list) -> None:
    """Serialize node and its entire subtree inline — no newlines added."""
    if isinstance(node, NavigableString):
        out.append(str(node))
    elif isinstance(node, Tag):
        tag = node.name
        out.append(f"<{tag}{attrs_str(node)}>")
        for child in node.children:
            serialize_inline(child, out)
        if tag not in VOID_TAGS:
            out.append(f"</{tag}>")


def clean_text(text: str) -> str:
    """Strip formatting-only newlines from a text node; preserve meaningful spaces."""
    t = _LEAD_NL.sub('', text)
    t = _TRAIL_NL.sub('', t)
    return t


def has_block_child(node: Tag) -> bool:
    return any(isinstance(c, Tag) and c.name in BLOCK_TAGS for c in node.children)


def serialize(node, depth: int, out: list) -> None:
    """Block elements on their own indented line; inline elements stay inline.

    Elements with only inline/text children are kept on one line.
    Elements with at least one block child use the multi-line format.
    """
    indent = '  ' * depth

    if isinstance(node, Doctype):
        out.append(f"<!DOCTYPE {node}>\n")
        return

    if isinstance(node, NavigableString):
        text = clean_text(str(node))
        if text:
            out.append(text)
        return

    if not isinstance(node, Tag):
        return

    tag     = node.name
    is_void = tag in VOID_TAGS

    if tag in BLOCK_TAGS:
        open_tag  = f"<{tag}{attrs_str(node)}>"
        close_tag = f"</{tag}>"
        if is_void:
            out.append(f"\n{indent}{open_tag}")
        elif has_block_child(node):
            out.append(f"\n{indent}{open_tag}")
            for child in node.children:
                if isinstance(child, NavigableString):
                    text = clean_text(str(child))
                    if text:
                        out.append(text)
                elif isinstance(child, Tag):
                    if child.name in BLOCK_TAGS:
                        serialize(child, depth + 1, out)
                    else:
                        serialize_inline(child, out)
            out.append(f"\n{indent}{close_tag}")
        else:
            # All children are inline/text: keep on one line
            out.append(f"\n{indent}{open_tag}")
            for child in node.children:
                if isinstance(child, NavigableString):
                    text = clean_text(str(child))
                    if text:
                        out.append(text)
                else:
                    serialize_inline(child, out)
            out.append(close_tag)
    else:
        serialize_inline(node, out)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Reading {INPUT_PATH} ...")
    html_text = INPUT_PATH.read_text(encoding='utf-8')

    print("Parsing HTML ...")
    soup = BeautifulSoup(html_text, 'html.parser')

    print("Building UUID → semantic ID mapping ...")
    mapping   = build_mapping(soup)
    sup_count = sum(1 for v in mapping.values() if not v.startswith('TABLE_NOTE_'))
    tbl_count = sum(1 for v in mapping.values() if v.startswith('TABLE_NOTE_'))
    print(f"  {sup_count} <sup> footnote references mapped")
    print(f"  {tbl_count} table-asterisk notes mapped")
    print(f"  {len(mapping)} total")

    print("\nSample mappings:")
    for uuid, sem in list(mapping.items())[:10]:
        print(f"  {uuid[:8]}…  →  {sem}")

    print("\nReplacing UUIDs in HTML source ...")
    # "(#?)" captures the optional # that precedes a UUID in href="#UUID" vs id="UUID"
    pattern = re.compile(
        '"(#?)(' + '|'.join(re.escape(u) for u in mapping) + ')"'
    )
    replaced_count = [0]

    def replacer(m):
        replaced_count[0] += 1
        prefix = m.group(1)   # '#' for href attributes, '' for id attributes
        uuid   = m.group(2)
        return f'"{prefix}{mapping[uuid]}"'

    new_html = pattern.sub(replacer, html_text)
    print(f"  {replaced_count[0]} attribute occurrences replaced")

    remaining = {m for m in UUID_SCAN.findall(new_html) if m not in DOC_UUIDS}
    if remaining:
        print(f"  WARNING: {len(remaining)} UUIDs still present in output:")
        for r in list(remaining)[:5]:
            print(f"    {r}")
    else:
        print("  All footnote UUIDs replaced successfully")

    print("\nRe-parsing for serialization ...")
    new_soup = BeautifulSoup(new_html, 'html.parser')

    print("Serializing with clean indentation ...")
    out = []
    for child in new_soup.children:
        serialize(child, 0, out)
    result = ''.join(out)

    print(f"Writing {OUTPUT_PATH} ...")
    OUTPUT_PATH.write_text(result, encoding='utf-8')

    lines = result.count('\n')
    print(f"\nDone.  Output: {lines:,} lines  |  {len(result):,} characters")


if __name__ == '__main__':
    main()
