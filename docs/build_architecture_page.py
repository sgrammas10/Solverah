"""Render docs/ARCHITECTURE.md into a designed standalone HTML artifact.

Converting rather than hand-transcribing keeps the published page and the
in-repo source of truth from drifting: re-running this after an edit to the
markdown reproduces the page exactly.
"""

import html
import re
import sys

SRC = "docs/ARCHITECTURE.md"
OUT = sys.argv[1] if len(sys.argv) > 1 else "architecture.html"


# ----------------------------------------------------------------- inline
def inline(text):
    """Convert inline markdown to HTML, escaping everything else.

    Code spans are swapped for placeholders rather than emitted immediately, so
    emphasis that *spans* a code span still pairs up -- e.g.
    ``**All pages are imported in `App.tsx`**``. Emitting the code span inline
    would split the bold markers across separate segments and leave them raw.
    """
    spans = []

    def _stash(m):
        spans.append(html.escape(m.group(1)))
        return "\x00%d\x00" % (len(spans) - 1)

    stashed = re.sub(r"`([^`]+)`", _stash, text)
    rendered = _emphasis(html.escape(stashed))
    return re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % spans[int(m.group(1))], rendered)


def _emphasis(escaped):
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                     r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", escaped)
    return escaped


def slugify(text):
    s = re.sub(r"<[^>]+>", "", text)
    s = re.sub(r"[^\w\s-]", "", s.replace("—", " ").replace("·", " "))
    return re.sub(r"[\s_]+", "-", s.strip()).lower()[:60]


# Severity prefix in Part 1.2 headings -> a chip the eye can triage on.
SEVERITY = re.compile(r"^(P[012])-(\d+)\s*[·•]\s*(.+)$")


def render(md):
    lines = md.split("\n")
    body, toc = [], []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        # fenced code
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            label = ('<span class="code-lang">%s</span>' % html.escape(lang)) if lang else ""
            body.append('<figure class="code">%s<pre><code>%s</code></pre></figure>'
                        % (label, html.escape("\n".join(buf))))
            continue

        # table (may be indented when it sits inside a list item)
        if (
            line.lstrip().startswith("|")
            and i + 1 < n
            and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip())
        ):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join("<th>%s</th>" % inline(c) for c in head)
            tb = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r)
                         for r in rows)
            body.append('<div class="table-wrap"><table><thead><tr>%s</tr></thead>'
                        "<tbody>%s</tbody></table></div>" % (th, tb))
            continue

        # headings
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            sev = SEVERITY.match(text)
            if level == 1:
                body.append('<h1 class="doc-title">%s</h1>' % inline(text))
            elif sev:
                tier, num, rest = sev.groups()
                body.append(
                    '<h4 class="defect" id="%s"><span class="sev sev-%s">%s</span>'
                    '<span class="defect-n">%s</span>%s</h4>'
                    % (slugify(text), tier.lower(), tier, num, inline(rest))
                )
            else:
                sid = slugify(text)
                body.append("<h%d id='%s'>%s</h%d>" % (level, sid, inline(text), level))
                if level in (2, 3):
                    toc.append((level, sid, text))
            i += 1
            continue

        if re.match(r"^-{3,}$", line.strip()):
            body.append('<hr class="part-rule">')
            i += 1
            continue

        # lists
        bullet = re.match(r"^(\s*)([-*])\s+(.*)$", line)
        number = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if bullet or number:
            tag = "ul" if bullet else "ol"
            items, pat = [], (r"^(\s*)([-*])\s+(.*)$" if bullet else r"^(\s*)(\d+)\.\s+(.*)$")
            while i < n:
                mm = re.match(pat, lines[i])
                if mm:
                    items.append(mm.group(3))
                    i += 1
                elif (
                    lines[i].startswith(("  ", "\t"))
                    and lines[i].strip()
                    and items
                    # An indented table belongs to the list item but is a block,
                    # not prose: folding it into the text emits raw pipes.
                    and not lines[i].lstrip().startswith("|")
                ):
                    items[-1] += " " + lines[i].strip()   # continuation line
                    i += 1
                else:
                    break
            body.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue

        if not line.strip():
            i += 1
            continue

        # paragraph
        para = []
        while i < n and lines[i].strip() and not re.match(
            r"^(#{1,4}\s|```|\||-{3,}$|\s*[-*]\s|\s*\d+\.\s)", lines[i]
        ):
            para.append(lines[i].strip())
            i += 1
        if para:
            body.append("<p>%s</p>" % inline(" ".join(para)))

    return "\n".join(body), toc


def render_toc(toc):
    out, open_sub = [], False
    for level, sid, text in toc:
        label = re.sub(r"^Part \d+\s*—\s*", "", text)
        label = re.sub(r"^(Appendix [A-Z])\s*—\s*", r"\1 · ", label)
        if level == 2:
            if open_sub:
                out.append("</ul></li>")
                open_sub = False
            part = re.match(r"^Part (\d+)", text)
            num = part.group(1) if part else "&middot;"
            out.append('<li class="toc-part"><a href="#%s"><span class="toc-num">%s</span>'
                       "<span>%s</span></a><ul>" % (sid, num, html.escape(label)))
            open_sub = True
        else:
            sub = re.sub(r"^\d+\.\d+\s+", "", label)
            sub = re.sub(r"^Phase (\d+).*", r"Phase \1", sub)
            out.append('<li><a href="#%s">%s</a></li>' % (sid, html.escape(sub)))
    if open_sub:
        out.append("</ul></li>")
    return "".join(out)


SHELL = """<title>Solverah Architecture v2</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
/* Palette inherited from the product's own tokens (tailwind.config.js):
   cream / forest / ink. Severity colors are semantic and deliberately kept
   separate from the forest accent so "critical" never reads as "brand". */
:root {
  --ground:        #FAF7F2;
  --surface:       #FFFFFF;
  --sunken:        #F2EDE5;
  --line:          #DED8CF;
  --line-soft:     #EAE4DB;
  --ink:           #1A1A1A;
  --ink-2:         #4E4A45;
  --ink-3:         #8A847B;
  --accent:        #2D6A4F;
  --accent-deep:   #1B4332;
  --accent-wash:   #E7F0EA;
  --sev-p0:        #8C2F26;
  --sev-p1:        #9A6516;
  --sev-p2:        #6E6A63;
  --sev-p0-bg:     #F6E4E1;
  --sev-p1-bg:     #F6EBD8;
  --sev-p2-bg:     #EBE8E2;

  --display: "Playfair Display", Georgia, "Times New Roman", serif;
  --sans: "DM Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;

  --measure: 74ch;
  --rail: 16.5rem;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:      #131714;
    --surface:     #1A201C;
    --sunken:      #10140F;
    --line:        #2E3831;
    --line-soft:   #242C26;
    --ink:         #E9E5DC;
    --ink-2:       #B3AEA3;
    --ink-3:       #7E877F;
    --accent:      #6FCF9B;
    --accent-deep: #9BE0BC;
    --accent-wash: #1D2A22;
    --sev-p0:      #E98D80;
    --sev-p1:      #DDB264;
    --sev-p2:      #9A968D;
    --sev-p0-bg:   #33201D;
    --sev-p1-bg:   #322817;
    --sev-p2-bg:   #232722;
  }
}
:root[data-theme="dark"] {
  --ground:      #131714;
  --surface:     #1A201C;
  --sunken:      #10140F;
  --line:        #2E3831;
  --line-soft:   #242C26;
  --ink:         #E9E5DC;
  --ink-2:       #B3AEA3;
  --ink-3:       #7E877F;
  --accent:      #6FCF9B;
  --accent-deep: #9BE0BC;
  --accent-wash: #1D2A22;
  --sev-p0:      #E98D80;
  --sev-p1:      #DDB264;
  --sev-p2:      #9A968D;
  --sev-p0-bg:   #33201D;
  --sev-p1-bg:   #322817;
  --sev-p2-bg:   #232722;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.68;
  -webkit-font-smoothing: antialiased;
}

.masthead {
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  padding: 3.5rem 1.5rem 2.75rem;
}
.masthead-inner { max-width: 78rem; margin: 0 auto; display: flex; flex-direction: column; gap: .9rem; }
.eyebrow {
  font-family: var(--mono);
  font-size: .70rem;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--accent);
  display: flex; flex-wrap: wrap; gap: .5rem 1.1rem; align-items: baseline;
}
.eyebrow .dot { color: var(--ink-3); }
.masthead h1 {
  font-family: var(--display);
  font-weight: 600;
  font-size: clamp(2.1rem, 5.2vw, 3.4rem);
  line-height: 1.08;
  letter-spacing: -.015em;
  margin: 0;
  text-wrap: balance;
}
.standfirst {
  font-size: 1.06rem;
  color: var(--ink-2);
  max-width: 60ch;
  margin: 0;
}
.facts {
  display: flex; flex-wrap: wrap; gap: 0 2.25rem;
  margin-top: .85rem; padding-top: 1.25rem;
  border-top: 1px solid var(--line-soft);
}
.fact { display: flex; flex-direction: column; gap: .1rem; padding: .35rem 0; }
.fact dt {
  font-family: var(--mono); font-size: .66rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--ink-3);
}
.fact dd {
  margin: 0; font-family: var(--mono); font-size: 1.02rem; font-weight: 500;
  font-variant-numeric: tabular-nums; color: var(--ink);
}
.fact dd.good { color: var(--accent); }

.shell {
  max-width: 78rem; margin: 0 auto; padding: 0 1.5rem 6rem;
  display: grid; grid-template-columns: var(--rail) minmax(0, 1fr); gap: 3.5rem;
  align-items: start;
}
@media (max-width: 60rem) { .shell { grid-template-columns: minmax(0, 1fr); gap: 0; } }

nav.toc {
  position: sticky; top: 0; align-self: start;
  max-height: 100vh; overflow-y: auto;
  padding: 2.5rem .5rem 3rem 0;
  border-right: 1px solid var(--line-soft);
  font-size: .855rem;
}
@media (max-width: 60rem) {
  nav.toc {
    position: static; max-height: none; border-right: 0;
    border-bottom: 1px solid var(--line); padding: 1.75rem 0;
  }
}
nav.toc h2 {
  font-family: var(--mono); font-size: .66rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--ink-3);
  margin: 0 0 1.1rem; font-weight: 500;
}
nav.toc ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
nav.toc > ul { gap: .3rem; }
nav.toc a {
  color: var(--ink-2); text-decoration: none; display: flex; gap: .6rem;
  padding: .2rem 0; border-radius: 2px;
}
nav.toc a:hover { color: var(--accent); }
nav.toc a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.toc-part > a { color: var(--ink); font-weight: 500; }
.toc-num {
  font-family: var(--mono); font-size: .7rem; color: var(--accent);
  min-width: 1.1rem; padding-top: .18rem; font-variant-numeric: tabular-nums;
}
.toc-part > ul {
  gap: .05rem; margin: .25rem 0 .75rem 1.7rem;
  border-left: 1px solid var(--line-soft); padding-left: .8rem;
}
.toc-part > ul a { font-size: .81rem; color: var(--ink-3); }
.toc-part > ul a:hover { color: var(--accent); }

article { padding-top: 2.5rem; min-width: 0; max-width: var(--measure); }
article > * { margin-inline: 0; }

h2 {
  font-family: var(--display); font-weight: 600;
  font-size: clamp(1.65rem, 3.4vw, 2.15rem); line-height: 1.14;
  letter-spacing: -.01em; margin: 0 0 1.4rem; padding-top: .5rem;
  text-wrap: balance; scroll-margin-top: 1.5rem;
}
h3 {
  font-size: 1.06rem; font-weight: 700; letter-spacing: -.005em;
  margin: 2.9rem 0 .9rem; color: var(--ink); scroll-margin-top: 1.5rem;
}
h3::before {
  content: ""; display: block; width: 1.75rem; height: 2px;
  background: var(--accent); margin-bottom: .7rem; opacity: .55;
}
h4 { font-size: .98rem; font-weight: 700; margin: 2.1rem 0 .7rem; scroll-margin-top: 1.5rem; }

h4.defect {
  display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
  margin-top: 2.5rem; padding-top: 1.1rem; border-top: 1px solid var(--line-soft);
}
.sev {
  font-family: var(--mono); font-size: .66rem; font-weight: 700;
  letter-spacing: .09em; padding: .17rem .45rem; border-radius: 3px;
}
.sev-p0 { color: var(--sev-p0); background: var(--sev-p0-bg); }
.sev-p1 { color: var(--sev-p1); background: var(--sev-p1-bg); }
.sev-p2 { color: var(--sev-p2); background: var(--sev-p2-bg); }
.defect-n {
  font-family: var(--mono); font-size: .8rem; color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}

p { margin: 0 0 1.15rem; }
article > p:first-of-type { margin-top: 0; }
a { color: var(--accent); text-underline-offset: .18em; text-decoration-thickness: 1px; }

ul, ol { margin: 0 0 1.3rem; padding-left: 1.35rem; }
li { margin-bottom: .5rem; }
li::marker { color: var(--ink-3); }
ol > li::marker { font-family: var(--mono); font-size: .85em; }

strong { font-weight: 700; }
code {
  font-family: var(--mono); font-size: .855em;
  background: var(--sunken); border: 1px solid var(--line-soft);
  padding: .07em .34em; border-radius: 3px; word-break: break-word;
}

figure.code {
  position: relative; margin: 0 0 1.6rem;
  background: var(--sunken); border: 1px solid var(--line);
  border-radius: 4px; overflow: hidden;
}
figure.code pre { margin: 0; padding: 1.15rem 1.25rem; overflow-x: auto; }
figure.code code {
  background: none; border: 0; padding: 0; font-size: .795rem;
  line-height: 1.62; white-space: pre; color: var(--ink-2);
}
.code-lang {
  position: absolute; top: 0; right: 0;
  font-family: var(--mono); font-size: .6rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--ink-3);
  padding: .3rem .6rem; background: var(--surface);
  border-left: 1px solid var(--line); border-bottom: 1px solid var(--line);
  border-bottom-left-radius: 4px;
}

.table-wrap { overflow-x: auto; margin: 0 0 1.7rem; border-bottom: 1px solid var(--line); }
table { border-collapse: collapse; width: 100%; font-size: .875rem; }
thead th {
  text-align: left; font-family: var(--mono); font-weight: 500;
  font-size: .655rem; letter-spacing: .13em; text-transform: uppercase;
  color: var(--ink-3); padding: .5rem .85rem .5rem 0;
  border-bottom: 1px solid var(--line); white-space: nowrap;
}
tbody td {
  padding: .62rem .85rem .62rem 0; border-bottom: 1px solid var(--line-soft);
  vertical-align: top; color: var(--ink-2); font-variant-numeric: tabular-nums;
}
tbody tr:last-child td { border-bottom: 0; }
tbody td:first-child { color: var(--ink); font-weight: 500; }
tbody td code { font-size: .8em; }

hr.part-rule {
  border: 0; height: 1px; background: var(--line);
  margin: 3.5rem 0 3rem;
}

footer.colophon {
  border-top: 1px solid var(--line); background: var(--surface);
  padding: 2.25rem 1.5rem 3rem; color: var(--ink-3);
  font-family: var(--mono); font-size: .72rem; letter-spacing: .04em;
}
footer.colophon div { max-width: 78rem; margin: 0 auto; display: flex; flex-wrap: wrap; gap: .4rem 1.5rem; }
</style>

<header class="masthead">
  <div class="masthead-inner">
    <p class="eyebrow">
      <span>Solverah</span><span class="dot">/</span>
      <span>Architecture review</span><span class="dot">/</span>
      <span>v2 target</span><span class="dot">/</span>
      <span>22 Aug 2026</span>
    </p>
    <h1>Built for ten thousand, aimed at ten million</h1>
    <p class="standfirst">
      A defect-by-defect audit of the Solverah platform as it stands, and the
      target architecture, schema, API, and frontend that carry it to millions of
      users &mdash; with the migration path between the two.
    </p>
    <dl class="facts">
      <div class="fact"><dt>API surface</dt><dd>3,922 LOC &middot; 38 routes</dd></div>
      <div class="fact"><dt>Frontend</dt><dd>141 files &middot; 24,343 LOC</dd></div>
      <div class="fact"><dt>Schema</dt><dd>17 tables &middot; 15 migrations</dd></div>
      <div class="fact"><dt>Test baseline</dt><dd class="good">570 passing</dd></div>
    </dl>
  </div>
</header>

<div class="shell">
  <nav class="toc" aria-label="Contents">
    <h2>Contents</h2>
    <ul>__TOC__</ul>
  </nav>
  <article>__BODY__</article>
</div>

<footer class="colophon">
  <div>
    <span>Source of truth: docs/ARCHITECTURE.md</span>
    <span>&middot;</span>
    <span>Branch: causal_bayesian_model</span>
    <span>&middot;</span>
    <span>Phase 0 foundation landed &mdash; Phases 1&ndash;5 pending</span>
  </div>
</footer>
"""


def main():
    md = open(SRC, encoding="utf-8").read()
    # The masthead carries the title and metadata block; drop them from the flow.
    md = re.sub(r"\A#\s+.*?\n", "", md, count=1)
    md = re.sub(r"\A\s*\*\*Status:\*\*.*?\n", "", md, count=1)
    body, toc = render(md)
    page = SHELL.replace("__TOC__", render_toc(toc)).replace("__BODY__", body)
    open(OUT, "w", encoding="utf-8").write(page)
    print("wrote %s  (%d bytes, %d toc entries)" % (OUT, len(page), len(toc)))


main()
