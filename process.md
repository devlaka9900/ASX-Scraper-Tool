# HTML Document Cleanup — Reusable Process

## What this does

`fix_html.py` takes an HTML file produced by a PDF parser (with UUID-based footnote anchors and inconsistent indentation) and produces a clean, maintainable version:

1. **Renames footnote IDs** from opaque UUIDs to short, human-readable semantic IDs
2. **Fixes indentation** so the HTML structure is easy to read and navigate

Content is never changed — only ID attribute values and whitespace between elements.

---

## Prerequisites

- Python 3.8+
- BeautifulSoup4: `pip install beautifulsoup4`

---

## How to run

```
python fix_html.py
```

Output is written to `result_formatted.html` in the same folder as the input file.

### What the console output means

```
257 <sup> footnote references mapped   ← UUIDs found in the body via <sup><a href="#uuid">
  0 table-asterisk notes mapped        ← footnote <div>s with no body <sup> link
514 attribute occurrences replaced     ← href="#uuid" + id="uuid" replacements (257 × 2)
All footnote UUIDs replaced            ← no orphan UUIDs remain in the output
```

---

## Configuration — 3 things to change per document

Open `fix_html.py` and edit the **Configuration** section at the top:

```python
INPUT_PATH  = Path(r"path\to\input.html")
OUTPUT_PATH = INPUT_PATH.parent / "result_formatted.html"

DOC_UUIDS = {'8f4b0082-779f-11e9-ac50-64006a8e7d91'}   # UUID(s) NOT to rename

_ORG_PREFIX = re.compile(r'asx\s+24\s*', re.IGNORECASE)  # org prefix to strip from H2 text
```

| Setting | What it is | When to change |
|---|---|---|
| `INPUT_PATH` | Path to the source HTML file | Every new document |
| `OUTPUT_PATH` | Where to write the cleaned file | Optionally change filename |
| `DOC_UUIDS` | UUIDs that appear in `<title>` or elsewhere but are NOT footnotes | Each document has its own; find it in the `<title>` tag |
| `_ORG_PREFIX` | Regex stripped from H2 headings before extracting a keyword | Change if the doc is from a different organisation |

---

## ID naming convention

Every footnote gets a 3-part ID:

```
{DivSlug}-{H2Short}-{FootnoteNumber}
```

| Part | Source | Example |
|---|---|---|
| `DivSlug` | First alphabetic word of the nearest ancestor `<div>` class, Title-cased | `<div class="RULES">` → `Rules` |
| `H2Short` | First meaningful keyword + first section number from H2 heading, lowercase | `SECTION 1 ACCESS TO THE MARKET` → `section1` |
| `FootnoteNumber` | The visible marker in the `<sup>` link | `35`, `*`, `∗` |

**Examples from ASX 24:**

| Context | Generated ID |
|---|---|
| Section 1 footnote 5 | `Rules-section1-5` |
| Section 4 footnote 1 | `Rules-section4-1` |
| Schedule 1 asterisk footnote | `Rules-schedule1-*` |
| Guidance Note 1 footnote 35 | `Guidance-guidance1-35` |
| Guidance Note 10 footnote 32 | `Guidance-guidance10-32` |

If two different footnotes produce the same 3-part ID, the second and later ones get a numeric suffix: `Rules-section1-1_2`, `Rules-section1-1_3`, etc.

---

## How indentation works

The script uses a custom serializer (not BeautifulSoup's `prettify()`, which breaks inline elements).

**Block elements** — each on its own line, 2-space indent per nesting level:
`html`, `head`, `body`, `div`, `p`, `table`, `tbody`, `tr`, `td`, `h1`–`h6`, `ul`, `ol`, `li`, `meta`, `title`, `link`

**Inline elements** — kept on the same line as surrounding text, no extra newlines:
`sup`, `a`, `strong`, `em`, `span`, `b`, `i`

**Single-line rule** — if a block element contains only text and inline children (no nested block), the whole element is written on one line:
```html
<h2>SECTION 1 ACCESS TO THE MARKET</h2>
<p>Some text <sup><a href="#Rules-section1-1">1</a></sup> more text</p>
```

**Multi-line rule** — if a block element has at least one block child, children are each on their own indented line:
```html
<table border="1">
  <tbody>
    <tr>
      <td>
        <p>Cell content</p>
      </td>
    </tr>
  </tbody>
</table>
```

---

## Adapting for a different document — checklist

1. **Update paths** — set `INPUT_PATH` and (optionally) `OUTPUT_PATH`

2. **Find and set `DOC_UUIDS`** — open the input file, check the `<title>` tag for a UUID, add it to the set so it isn't renamed:
   ```python
   DOC_UUIDS = {'your-doc-uuid-here'}
   ```
   Set to an empty set `{}` if there are no non-footnote UUIDs.

3. **Update `_ORG_PREFIX`** — the regex removes a fixed string from the start of H2 headings before extracting the keyword. For a different organisation:
   ```python
   _ORG_PREFIX = re.compile(r'your org name\s*', re.IGNORECASE)
   ```
   Set to `re.compile(r'(?!)')` (never-match) to disable stripping entirely.

4. **Check `_STOP_WORDS`** — words too generic to be useful as an H2 keyword. Add any domain-specific filler words your document uses:
   ```python
   _STOP_WORDS = {'of','to','the', ... 'your','extra','words'}
   ```

5. **Check heading level** — if the document uses H1 instead of H2 for section headings, change the `if name == 'h2':` check in `build_mapping()` to `if name == 'h1':`.

6. **Run and review the sample mappings** printed to the console. If the H2Short part looks wrong (e.g. picks up the wrong word), adjust `_ORG_PREFIX` or `_STOP_WORDS`.

---

## Limitations

- Footnotes must be linked via `<sup><a href="#uuid">N</a></sup>` in the body. Bare asterisks in table cells with no `href` link cannot be auto-mapped (they'll keep their UUID or become `TABLE_NOTE_N`).
- The input file must be UTF-8 encoded. If the PDF parser produced a different encoding, convert first: `iconv -f WINDOWS-1252 -t UTF-8 input.html > input_utf8.html`
- Collision suffixes (`_2`, `_3`) appear when two genuinely different footnotes land in the same H2 section with the same number. This is rare in well-structured documents but possible in tables that span multiple sections.
