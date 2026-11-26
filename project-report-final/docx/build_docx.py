"""Build an editable Word version of the final report from the LaTeX sources.

Run inside the report's TeX container from project-report-final/, after the
PDF has been built (it reads main.aux for figure, table and section numbers):

    python3 docx/build_docx.py

Steps: inline the chapters; render every TikZ picture to a PNG; replace
figure/table captions and cross-references with the numbers LaTeX assigned;
convert with pandoc (citations via citeproc); then apply the course typography
(Times New Roman, 16/14/12 pt bold headings, 12 pt justified text at 1.5 line
spacing, centred captions, black text) and add the title page, the automatic
contents, list of figures and list of tables, and page numbers.
"""
import os
import re
import shutil
import subprocess
import sys

BS = "\\"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # project-report-final
WORK = os.path.join(HERE, "work")
OUT = os.path.join(ROOT, "MemoryLane_Final_Report.docx")
TEXT_WIDTH_IN = 6.27                    # A4 with 1 inch margins


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def balanced(text, start):
    """Index just after the brace group that opens at text[start] == '{'."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{" and text[i - 1] != BS:
            depth += 1
        elif c == "}" and text[i - 1] != BS:
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced braces at %d" % start)


# ---- 1. labels from the LaTeX build -------------------------------------------
def load_labels():
    labels = {}
    for line in read(os.path.join(ROOT, "main.aux")).splitlines():
        m = re.match(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", line)
        if m and not m.group(1).endswith("@cref"):
            labels[m.group(1)] = m.group(2)
    return labels


# ---- 2. inline \input files -------------------------------------------------------
def inline_inputs(text, depth=0):
    def repl(m):
        name = m.group(1)
        path = os.path.join(ROOT, name if name.endswith(".tex") else name + ".tex")
        return inline_inputs(read(path), depth + 1)
    return re.sub(r"\\input\{([^}]+)\}", repl, text)


# ---- 3. render TikZ pictures ---------------------------------------------------
def preamble():
    main = read(os.path.join(ROOT, "main.tex"))
    start = main.index(BS + "usepackage{graphicx}")
    end = main.index("% ==================================================\n% TITLE PAGE")
    pre = main[start:end]
    # biblatex and hyperref settings are not needed for a picture
    pre = re.sub(r"\\usepackage\[[^\]]*\]\{biblatex\}", "", pre, flags=re.S)
    pre = pre.replace(BS + "addbibresource{references.bib}", "")
    pre = pre.replace(BS + "hypersetup{hidelinks}", "")
    pre = pre.replace(BS + "raggedbottom", "").replace(BS + "setlength{" + BS + "headheight}{15pt}", "")
    return (BS + "documentclass[border=4pt,12pt]{standalone}\n" + BS + "usepackage{mathptmx}\n"
            + BS + "usepackage{amsmath,amssymb}\n" + pre)


def render_tikz(text):
    os.makedirs(os.path.join(WORK, "fig"), exist_ok=True)
    pre = preamble()
    out, pos, n = [], 0, 0
    begin, end_tag = BS + "begin{tikzpicture}", BS + "end{tikzpicture}"
    # display equations become pictures too, so every Word viewer shows them
    text = re.sub(r"\\begin\{align\*\}(.*?)\\end\{align\*\}",
                  lambda m: begin + "\\node{$\\displaystyle\\begin{aligned}" + m.group(1)
                  + "\\end{aligned}$};" + end_tag, text, flags=re.S)
    while True:
        i = text.find(begin, pos)
        if i < 0:
            out.append(text[pos:])
            break
        # keep \newcommand / \tikzset lines that precede the picture inside the figure
        j = text.index(end_tag, i) + len(end_tag)
        n += 1
        name = "fig-%02d" % n
        src = pre + "\n" + BS + "begin{document}\n" + text[i:j] + "\n" + BS + "end{document}\n"
        write(os.path.join(WORK, "fig", name + ".tex"), src)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", name + ".tex"],
                       cwd=os.path.join(WORK, "fig"), stdout=subprocess.DEVNULL, check=True)
        subprocess.run(["pdftoppm", "-r", "220", "-png", "-singlefile", name + ".pdf", name],
                       cwd=os.path.join(WORK, "fig"), check=True)
        info = subprocess.run(["pdfinfo", name + ".pdf"], cwd=os.path.join(WORK, "fig"),
                              capture_output=True, text=True).stdout
        w_pt = float(re.search(r"Page size:\s+([\d.]+) x", info).group(1))
        width = min(w_pt / 72.0, TEXT_WIDTH_IN)
        out.append(text[pos:i])
        out.append(BS + "includegraphics[width=%.2fin]{docx/work/fig/%s.png}" % (width, name))
        pos = j
    print("rendered", n, "TikZ pictures")
    return "".join(out)


# ---- 4. simplify LaTeX for pandoc --------------------------------------------------
def numbered_captions(text, labels):
    """Give each figure/table caption its LaTeX number and drop the label."""
    out, pos = [], 0
    for m in re.finditer(r"\\begin\{(figure|table|longtable)\}", text):
        pass
    env_re = re.compile(r"\\begin\{(figure|table|longtable)\}")
    pos = 0
    result = []
    while True:
        m = env_re.search(text, pos)
        if not m:
            result.append(text[pos:])
            break
        kind = m.group(1)
        end = text.index(BS + "end{" + kind + "}", m.end())
        body = text[m.start():end]
        lab = re.search(r"\\label\{([^}]+)\}", body)
        number = labels.get(lab.group(1)) if lab else None
        word = "Figure" if kind == "figure" else "Table"
        # main caption = the last \caption in the environment
        caps = [c.start() for c in re.finditer(re.escape(BS) + "caption\\{", body)]
        if caps and number:
            c0 = caps[-1]
            c1 = balanced(body, c0 + len(BS + "caption"))
            cap_text = body[c0 + len(BS + "caption") + 1:c1 - 1]
            body = body[:c0] + BS + "caption{" + "%s %s: %s" % (word, number, cap_text) + "}" + body[c1:]
        # sub-captions become an italic line under their image
        if kind == "figure":
            letters = iter("abcdefgh")
            def sub(mm):
                return ""
            parts = re.split(r"(\\begin\{subfigure\}(?:\[[^\]]*\])?\{[^}]*\}|\\end\{subfigure\})", body)
            rebuilt, in_sub = [], False
            for p in parts:
                if p.startswith(BS + "begin{subfigure}"):
                    in_sub = True
                    continue
                if p == BS + "end{subfigure}":
                    in_sub = False
                    continue
                if in_sub:
                    k = p.find(BS + "caption{")
                    if k >= 0:
                        k1 = balanced(p, k + len(BS + "caption"))
                        sc = p[k + len(BS + "caption") + 1:k1 - 1]
                        p = p[:k] + "\n\n" + BS + "emph{(" + next(letters) + ") " + sc + "}\n\n" + p[k1:]
                rebuilt.append(p)
            body = "".join(rebuilt)
        body = re.sub(r"\\label\{[^}]+\}", "", body)
        result.append(text[pos:m.start()] + body)
        pos = end
    return "".join(result)


def column_kinds(spec):
    """Each column of a tabular spec: a width fraction (p-columns), 'flex' (X/L) or 'short' (l/c/r)."""
    kinds, i = [], 0
    while i < len(spec):
        c = spec[i]
        if c in "><@!" and i + 1 < len(spec) and spec[i + 1] == "{":
            i = balanced(spec, i + 1)
            continue
        if c in "pmb" and i + 1 < len(spec) and spec[i + 1] == "{":
            end = balanced(spec, i + 1)
            arg = spec[i + 2:end - 1]
            m = re.match(r"\s*([0-9.]*)\s*\\(?:textwidth|linewidth|hsize)", arg)
            if m:
                kinds.append(float(m.group(1) or 1))
            else:
                m = re.match(r"\s*([0-9.]+)\s*(cm|mm|in|pt|em)", arg)
                per = {"cm": 1 / 16.0, "mm": 1 / 160.0, "in": 2.54 / 16, "pt": 2.54 / 72 / 16, "em": 0.42 / 16}
                kinds.append(float(m.group(1)) * per[m.group(2)] if m else "flex")
            i = end
            continue
        if c in "XL":
            kinds.append("flex")
        elif c in "lcr":
            kinds.append("short")
        i += 1
    return kinds


TABLE_WIDTHS = []  # column fractions per table, in document order, applied in finish()


def column_spec(spec):
    """Explicit p{} widths summing to the text width, so Word lays tables out full width."""
    kinds = column_kinds(spec) or ["flex"]
    short = 0.10
    # Word cells have padding, so very narrow id columns would wrap "FR-01"
    kinds = [max(k, 0.09) if isinstance(k, float) else k for k in kinds]
    fixed = sum(k for k in kinds if isinstance(k, float)) + short * kinds.count("short")
    flex = kinds.count("flex")
    rest = max(1.0 - fixed, 0.15 * flex) / flex if flex else 0
    widths = [k if isinstance(k, float) else (short if k == "short" else rest) for k in kinds]
    total = sum(widths)
    widths = [w / total for w in widths]
    return widths, "".join("p{%.3f" % w + BS + "textwidth}" for w in widths)


def normalize_tables(text):
    """Plain column specs that pandoc understands; tabularx becomes tabular.

    Also records each table's column widths in document order (TABLE_WIDTHS). A table
    inside the \\usecase macro definition is recorded once per use of the macro instead.
    """
    out, pos, found = [], 0, []
    macro = text.find(BS + "newcommand{" + BS + "usecase}")
    macro_end = balanced(text, text.index("{", macro + len(BS + "newcommand{" + BS + "usecase}"))) if macro >= 0 else -1
    usecase_widths = None
    pat = re.compile(r"\\begin\{(tabularx|longtable|tabular)\}")
    while True:
        m = pat.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        env, j = m.group(1), m.end()
        if env == "tabularx":           # skip the width argument
            j = balanced(text, j)
        spec_end = balanced(text, j)
        spec = text[j + 1:spec_end - 1]
        new_env = "tabular" if env == "tabularx" else env
        widths, newspec = column_spec(spec)
        if macro <= m.start() < macro_end:
            usecase_widths = widths
        else:
            found.append((m.start(), widths))
        out.append(text[pos:m.start()] + BS + "begin{" + new_env + "}{" + newspec + "}")
        pos = spec_end
    if usecase_widths:
        for u in re.finditer(r"\\usecase\{", text):
            if not (macro <= u.start() < macro_end):
                found.append((u.start(), usecase_widths))
    TABLE_WIDTHS[:] = [w for _, w in sorted(found)]
    text = "".join(out)
    return text.replace(BS + "end{tabularx}", BS + "end{tabular}")


MATH_WORDS = {"rightarrow": "→", "bullet": "•", "ll": "≪", "gg": "≫", "geq": "≥",
              "leq": "≤", "cdot": "·", "times": "×", "approx": "≈"}


def plain_math(text):
    """Inline $...$ as ordinary text: LibreOffice and older Word drop simple equation objects."""
    def conv(m):
        s = m.group(1)
        s = re.sub(BS + BS + r"text\{([^}]*)\}", lambda c: c.group(1), s)
        s = re.sub(BS + BS + r"([a-zA-Z]+)\s*", lambda c: MATH_WORDS.get(c.group(1), c.group(0)), s)
        s = re.sub(r"_\{([^}]*)\}|_(\w)", lambda c: BS + "textsubscript{" + (c.group(1) or c.group(2)) + "}", s)
        s = s.replace("-", "−") if s.startswith("-") else s
        if re.fullmatch(r"[A-Za-z]", s) or re.fullmatch(r"[A-Za-z]" + BS + BS + r"textsubscript\{\w+\}", s):
            return BS + "textit{" + s + "}"
        return s
    return re.sub(r"(?<!" + BS + BS + r")\$([^$]+)\$", conv, text)


def simplify(text, labels):
    text = text[text.index(BS + "begin{document}") + len(BS + "begin{document}"):text.index(BS + "end{document}")]
    text = normalize_tables(text)
    # code listings as plain verbatim blocks (pandoc then uses the Source Code style)
    text = re.sub(r"\\begin\{lstlisting\}(\[[^\]]*\])?", lambda m: BS + "begin{verbatim}", text)
    text = text.replace(BS + "end{lstlisting}", BS + "end{verbatim}")
    text = text.replace(BS + "maketitle", "")
    for cmd in ["tableofcontents", "listoffigures", "listoftables", "clearpage", "cleardoublepage"]:
        text = text.replace(BS + cmd, "")
    text = re.sub(r"\\pagenumbering\{[^}]*\}", "", text)
    text = re.sub(r"\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}", "", text)
    # screenshots
    def shot(m):
        w = m.group(1) or "1"
        frac = float(w.replace(BS + "textwidth", "").strip() or 1)
        return BS + "includegraphics[width=%.2fin]{%s}" % (frac * TEXT_WIDTH_IN, m.group(2))
    text = re.sub(r"\\screenshot\[([^\]]*)\]\{([^}]*)\}\{[^}]*\}", shot, text)
    text = render_tikz(text)
    text = plain_math(text)
    text = numbered_captions(text, labels)
    text = re.sub(r"\\(?:ref|autoref)\{([^}]+)\}", lambda m: labels.get(m.group(1), "?"), text)
    text = re.sub(r"\\path\{([^}]*)\}", lambda m: BS + "texttt{" + m.group(1).replace("_", BS + "_") + "}", text)
    # run-in paragraph headings become bold lead-ins
    text = re.sub(r"\\paragraph\{([^}]*)\}", lambda m: BS + "textbf{" + m.group(1) + "} ", text)
    # bibliography and appendices
    text = text.replace(BS + "printbibliography[heading=bibintoc]", BS + "chapter*{References}\n")
    head, _, tail = text.partition(BS + "appendix")
    letters = iter("ABCDEFG")
    tail = re.sub(r"\\chapter\{([^}]*)\}", lambda m: BS + "chapter*{Appendix " + next(letters) + ": " + m.group(1) + "}", tail)
    return head + tail


# ---- 5. reference document with the course styles ----------------------------------
def make_reference(path):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor, Inches
    subprocess.run(["pandoc", "-o", path, "--print-default-data-file", "reference.docx"], check=True)
    doc = Document(path)
    black = RGBColor(0, 0, 0)

    def style(name, size, bold=False, align=None, spacing=1.5, italic=False, before=None, after=None):
        try:
            s = doc.styles[name]
        except KeyError:
            return
        f = s.font
        f.name, f.size, f.bold, f.italic, f.color.rgb = "Times New Roman", Pt(size), bold, italic, black
        rpr = s.element.get_or_add_rPr()
        fonts = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
        if fonts is not None:
            for a in list(fonts.attrib):
                if "Theme" in a or "theme" in a:
                    del fonts.attrib[a]
            for a in ("ascii", "hAnsi", "cs", "eastAsia"):
                fonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}" + a, "Times New Roman")
        if not hasattr(s, "paragraph_format"):
            return  # character style: font only
        pf = s.paragraph_format
        if align is not None:
            pf.alignment = align
        pf.line_spacing = spacing
        if before is not None:
            pf.space_before = Pt(before)
        if after is not None:
            pf.space_after = Pt(after)

    J, C, L = WD_ALIGN_PARAGRAPH.JUSTIFY, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT
    for name in ["Normal", "Body Text", "First Paragraph", "Block Text", "Bibliography"]:
        style(name, 12, align=J, after=6)
    style("Compact", 11, align=L, spacing=1.0, after=0)
    style("Heading 1", 16, bold=True, align=L, before=12, after=12)
    style("Heading 2", 14, bold=True, align=L, before=12, after=6)
    style("Heading 3", 12, bold=True, align=L, before=10, after=6)
    style("Heading 4", 12, bold=True, align=L, before=8, after=4)
    style("Title", 16, bold=True, align=C)
    style("Subtitle", 14, align=C)
    for name in ["Caption", "Image Caption", "Table Caption"]:
        style(name, 12, align=C, after=10)
    style("Captioned Figure", 12, align=C)
    style("Figure", 12, align=C)
    style("Source Code", 11, align=L, spacing=1.0)
    style("Verbatim Char", 11)
    for name in ["Hyperlink", "Footnote Text"]:
        try:
            doc.styles[name].font.color.rgb = black
            doc.styles[name].font.name = "Times New Roman"
        except KeyError:
            pass
    doc.styles["Heading 1"].paragraph_format.page_break_before = True
    for sec in doc.sections:
        sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
        sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
    doc.save(path)


# ---- 6. finishing touches in Word -----------------------------------------------------
def finish(path):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, Inches, RGBColor

    doc = Document(path)
    body = doc.element.body
    first = doc.paragraphs[0]

    def para_before(anchor, text="", size=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                    space_after=0, italic=False, style=None):
        p = anchor.insert_paragraph_before("", style=style)
        p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = 1.15
        if text:
            r = p.add_run(text)
            r.font.name, r.font.size, r.bold, r.italic = "Times New Roman", Pt(size), bold, italic
            r.font.color.rgb = RGBColor(0, 0, 0)
        return p

    # title page (the current report's details, laid out as in the course format)
    logo = os.path.join(os.path.dirname(ROOT), "assets", "tiet-logo.png")
    lines = [
        ("MemoryLane", 20, True, 4),
        ("A Personal Web Memory with Hybrid Semantic Search", 14, False, 18),
        ("Final Project Report", 16, True, 6),
        ("Submitted for the End Semester Evaluation of", 12, False, 0),
        ("UCS503 Software Engineering Lab", 12, True, 30),
        ("Submitted by", 13, True, 6),
        ("Rabeeh Ahmad    1024030716", 12, False, 0),
        ("Ishan Singhania    1024030719", 12, False, 6),
        ("Group 3C51    BE Third Year, Computer Science and Engineering", 12, False, 30),
        ("Submitted to", 13, True, 6),
        ("Dr. Raghav B. Venkataramaiyer", 12, False, 30),
    ]
    if os.path.exists(logo):
        p = para_before(first, space_after=24)
        p.add_run().add_picture(logo, width=Inches(1.6))
    for text, size, bold, after in lines:
        para_before(first, text, size, bold, space_after=after)
    for text in ["COMPUTER SCIENCE AND ENGINEERING DEPARTMENT",
                 "THAPAR INSTITUTE OF ENGINEERING AND TECHNOLOGY", "PATIALA 147004"]:
        para_before(first, text, 12, True)
    p = para_before(first, "November 2026", 12, False, space_after=0)
    p.add_run().add_break(WD_BREAK.PAGE)

    # automatic contents, list of figures and list of tables before the abbreviations
    def field_paragraph(anchor, instr):
        p = anchor.insert_paragraph_before("")
        r = p.add_run()
        for kind, text in [("begin", None), (None, instr), ("separate", None), (None, None), ("end", None)]:
            if kind:
                fc = OxmlElement("w:fldChar")
                fc.set(qn("w:fldCharType"), kind)
                r._r.append(fc)
            elif text:
                it = OxmlElement("w:instrText")
                it.set(qn("xml:space"), "preserve")
                it.text = text
                r._r.append(it)
            else:
                t = OxmlElement("w:t")
                t.text = "Right-click and choose Update Field."
                r._r.append(t)
        return p

    abbrev = next(p for p in doc.paragraphs if p.text.strip() == "List of Abbreviations")
    for title, instr in [("Contents", 'TOC \\o "1-3" \\h \\z \\u'),
                         ("List of Figures", 'TOC \\h \\z \\t "Image Caption,1"'),
                         ("List of Tables", 'TOC \\h \\z \\t "Table Caption,1"')]:
        h = abbrev.insert_paragraph_before(title, style="Heading 1")
        field_paragraph(abbrev, instr)

    # page numbers in the footer
    for sec in doc.sections:
        fp = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run()
        for kind, text in [("begin", None), (None, "PAGE"), ("end", None)]:
            if kind:
                fc = OxmlElement("w:fldChar")
                fc.set(qn("w:fldCharType"), kind)
                r._r.append(fc)
            else:
                it = OxmlElement("w:instrText")
                it.text = text
                r._r.append(it)
        r.font.name, r.font.size = "Times New Roman", Pt(12)

    # every editable run in Times New Roman and black; tables full width
    for p in doc.paragraphs:
        code = p.style is not None and p.style.name == "Source Code"
        if code:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            if code or (r.style is not None and r.style.name == "Verbatim Char"):
                r.font.name = "Courier New"
            else:
                r.font.name = "Times New Roman"
            r.font.color.rgb = RGBColor(0, 0, 0)
    usable = 9026  # A4 text width in twips (8.27in - 2in margins)
    print("tables: %d in Word, specs %s" % (len(doc.tables), [len(w) for w in TABLE_WIDTHS]))
    n = 0
    for t in doc.tables:
        ncols = len(t.columns)
        if t._tbl.findall('.//' + qn('w:drawing')):
            continue  # a row of subfigure images, not a LaTeX table
        if n < len(TABLE_WIDTHS) and len(TABLE_WIDTHS[n]) == ncols:
            widths = TABLE_WIDTHS[n]
        else:
            print("table %d: no matching widths (%d columns)" % (n, ncols))
            widths = [1.0 / ncols] * ncols
        n += 1
        twips = [int(w * usable) for w in widths]
        tblPr = t._tbl.tblPr
        for tag in ("w:tblW", "w:tblLayout"):
            for old in tblPr.findall(qn(tag)):
                tblPr.remove(old)
        tblW = OxmlElement("w:tblW"); tblW.set(qn("w:w"), str(usable)); tblW.set(qn("w:type"), "dxa")
        layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "fixed")
        tblPr.append(tblW); tblPr.append(layout)
        for gc, w in zip(t._tbl.tblGrid.findall(qn("w:gridCol")), twips):
            gc.set(qn("w:w"), str(w))
        for tr in t._tbl.findall(qn("w:tr")):
            for i, tc in enumerate(tr.findall(qn("w:tc"))):
                tcPr = tc.get_or_add_tcPr()
                span = tcPr.find(qn("w:gridSpan"))
                k = int(span.get(qn("w:val"))) if span is not None else 1
                for old in tcPr.findall(qn("w:tcW")):
                    tcPr.remove(old)
                tcW = OxmlElement("w:tcW"); tcW.set(qn("w:type"), "dxa")
                tcW.set(qn("w:w"), str(sum(twips[i:i + k]) if i < len(twips) else twips[-1]))
                tcPr.insert(0, tcW)
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.name = "Times New Roman"
                        r.font.color.rgb = RGBColor(0, 0, 0)

    # ask Word to refresh the contents and lists when the file is opened
    settings = doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)
    doc.save(path)


def main():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    labels = load_labels()
    text = simplify(inline_inputs(read(os.path.join(ROOT, "main.tex"))), labels)
    src = os.path.join(WORK, "report.tex")
    write(src, BS + "documentclass{report}\n" + BS + "begin{document}\n" + text + "\n" + BS + "end{document}\n")
    ref = os.path.join(WORK, "reference.docx")
    make_reference(ref)
    lua = os.path.join(HERE, "refs.lua")
    subprocess.run(["pandoc", src, "-f", "latex", "-o", OUT, "--reference-doc", ref,
                    "--lua-filter", lua, "--citeproc", "--bibliography", os.path.join(ROOT, "references.bib"),
                    "--number-sections", "--resource-path", ROOT + ":" + WORK + ":" + os.path.join(WORK, "fig")],
                   cwd=ROOT, check=True)
    finish(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
