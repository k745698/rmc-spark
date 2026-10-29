"""Build the manuscript (.docx) by filling the official VIT/IEEE consolidated template.

    python paper/build_paper.py --template path/to/3_Consolidated_Template.docx

Inputs : paper/content/*.txt (manuscript source), paper/refs/refs_keyed.json (verified references),
         paper/Diagrams/*.png (figures)
Output : paper/RMC-Spark_Manuscript.docx and paper/build_report.txt (word counts, checks)

Source syntax (one block per paragraph, blank line separated):
  @title / @abstract / @keywords          front matter
  @section T | @sub T | @unnumbered T      headings (roman / letter numbering automatic)
  @figure key | file stem | caption | wide? | placeholder?
  @table key | caption | wide|normal | col% list   followed by "| a | b |" rows (first = header)
  @equation key                           one of the OMML builders below
  @note text                              highlighted author note
  [@k1, @k2] citations -> [n][m];  {fig:k} {tab:k} {eq:k} cross references;  [[...]] placeholder
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import re
import shutil
import tempfile
import zipfile
from collections import OrderedDict

from lxml import etree
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = "{%s}" % W_NS
NSDECL = (f'xmlns:w="{W_NS}" xmlns:m="{M_NS}" xmlns:r="{R_NS}" '
          'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
          'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
          'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

TEAM_ID = "26FSPDSCPMID4098"
REGS = ["26MML0054", "26MML0006", "26MML0047", "26MML0015"]
OWNER = {  # section number -> register number (Contributions table); 0 = exec summary/abstract
    0: "26MML0015", 5: "26MML0015", 9: "26MML0015", 10: "26MML0015", 20: "26MML0015", 22: "26MML0015",
    8: "26MML0054", 11: "26MML0054", 14: "26MML0054", 15: "26MML0054", 19: "26MML0054", 21: "26MML0054",
    2: "26MML0006", 4: "26MML0006", 6: "26MML0006", 7: "26MML0006", 13: "26MML0006", 16: "26MML0006",
    1: "26MML0047", 3: "26MML0047", 12: "26MML0047", 17: "26MML0047", 18: "26MML0047",
}
APPENDIX_OWNER, REFERENCES_OWNER = "26MML0006", "26MML0047"

COL_TWIPS = (11906 - 2 * 1440 - 708) // 2      # 4159
WIDE_TWIPS = 11906 - 2 * 1440                    # 9026
EMU_PER_TWIP = 635

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII",
         "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV"]


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================================ source parsing
def parse_sources():
    blocks = []
    for path in sorted(glob.glob(os.path.join(HERE, "content", "*.txt"))):
        text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
        chunks = re.split(r"\n\s*\n", text)
        for ch in chunks:
            ch = ch.strip("\n")
            if not ch.strip():
                continue
            lines = ch.split("\n")
            head = lines[0]
            if head.startswith("@table"):
                parts = [p.strip() for p in head[len("@table"):].split("|")]
                rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines[1:] if ln.strip()]
                widths = [int(x) for x in parts[3].split(",")] if len(parts) > 3 and parts[3] else None
                blocks.append({"t": "table", "key": parts[0], "caption": parts[1], "wide": parts[2] == "wide",
                               "widths": widths, "rows": rows})
            elif head.startswith("@figure"):
                parts = [p.strip() for p in head[len("@figure"):].split("|")]
                blocks.append({"t": "figure", "key": parts[0], "file": parts[1], "caption": parts[2],
                               "wide": len(parts) > 3 and parts[3] == "wide",
                               "placeholder": "placeholder" in parts[3:]})
            elif head.startswith("@equation"):
                blocks.append({"t": "equation", "key": head.split()[1]})
            elif head.startswith("@section"):
                blocks.append({"t": "section", "text": head[len("@section"):].strip()})
            elif head.startswith("@sub"):
                blocks.append({"t": "sub", "text": head[len("@sub"):].strip()})
            elif head.startswith("@unnumbered"):
                blocks.append({"t": "unnumbered", "text": head[len("@unnumbered"):].strip()})
            elif head.startswith("@title"):
                blocks.append({"t": "title", "text": head[len("@title"):].strip()})
            elif head.startswith("@abstract"):
                blocks.append({"t": "abstract", "text": " ".join(lines[1:]).strip()})
            elif head.startswith("@keywords"):
                blocks.append({"t": "keywords", "text": head[len("@keywords"):].strip()})
            elif head.startswith("@note"):
                blocks.append({"t": "note", "text": " ".join(lines)[len("@note"):].strip()})
            else:
                blocks.append({"t": "para", "text": " ".join(l.strip() for l in lines)})
    return blocks


# ============================================================================ numbering
class Numbers:
    def __init__(self, blocks, refs):
        self.fig, self.tab, self.eq, self.cite = OrderedDict(), OrderedDict(), OrderedDict(), OrderedDict()
        self.refs = refs
        for b in blocks:
            if b["t"] == "figure":
                self.fig[b["key"]] = len(self.fig) + 1
            elif b["t"] == "table":
                self.tab[b["key"]] = len(self.tab) + 1
            elif b["t"] == "equation":
                self.eq[b["key"]] = len(self.eq) + 1
        # citation order = order of first appearance in reading order
        for b in blocks:
            for text in self._texts(b):
                for grp in re.findall(r"\[@([^\]]+)\]", text):
                    for k in re.findall(r"@?([\w-]+)", grp):
                        if k not in refs:
                            raise SystemExit(f"unknown citation key: {k}")
                        if k not in self.cite:
                            self.cite[k] = len(self.cite) + 1

    @staticmethod
    def _texts(b):
        if b["t"] == "table":
            yield b["caption"]
            for r in b["rows"]:
                yield from r
        elif "text" in b:
            yield b["text"]
        elif b["t"] == "figure":
            yield b["caption"]

    def resolve(self, text):
        def cites(m):
            keys = re.findall(r"@?([\w-]+)", m.group(1))
            nums = sorted(self.cite[k] for k in keys)
            return "".join(f"[{n}]" for n in nums)
        text = re.sub(r"\[@([^\]]+)\]", cites, text)

        def xref(m):
            kind, key = m.group(1), m.group(2)
            table = {"fig": self.fig, "tab": self.tab, "eq": self.eq}[kind]
            if key not in table:
                raise SystemExit(f"unknown cross reference {kind}:{key}")
            return str(table[key])
        return re.sub(r"\{(fig|tab|eq):([\w-]+)\}", xref, text)


# ============================================================================ run building
SUBSUP = re.compile(r"(?<![\w.\-/])([A-Za-zα-ωΑ-Ωτμσ])(\*?)_(\{[^}]+\}|[A-Za-z0-9]+)(\^(\{[^}]+\}|[A-Za-z0-9]+))?")


def rpr(sz=20, bold=False, italic=False, color=None, font=None, highlight=None, va=None, smallcaps=False):
    x = "<w:rPr>"
    if font:
        x += f'<w:rFonts w:ascii="{font}" w:eastAsia="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
    if bold:
        x += "<w:b/><w:bCs/>"
    if italic:
        x += "<w:i/><w:iCs/>"
    if smallcaps:
        x += "<w:smallCaps/>"
    if color:
        x += f'<w:color w:val="{color}"/>'
    x += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    if highlight:
        x += f'<w:highlight w:val="{highlight}"/>'
    if va:
        x += f'<w:vertAlign w:val="{va}"/>'
    return x + "</w:rPr>"


def run(text, **kw):
    if text == "":
        return ""
    return f'<w:r>{rpr(**kw)}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def rich_runs(text, **kw):
    """Text -> runs with [[placeholder]] highlighting and x_{sub}^{sup} notation."""
    out = []
    for i, part in enumerate(re.split(r"(\[\[.*?\]\])", text)):
        if not part:
            continue
        hl = part.startswith("[[") and part.endswith("]]")
        seg_kw = dict(kw, highlight="yellow") if hl else kw
        pos = 0
        for m in SUBSUP.finditer(part):
            out.append(run(part[pos:m.start()], **seg_kw))
            out.append(run(m.group(1) + m.group(2), **seg_kw))
            out.append(run(m.group(3).strip("{}"), **dict(seg_kw, va="subscript")))
            if m.group(4):
                out.append(run(m.group(5).strip("{}"), **dict(seg_kw, va="superscript")))
            pos = m.end()
        out.append(run(part[pos:], **seg_kw))
    return "".join(out)


BODY_PPR = ('<w:pPr><w:pBdr><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/>'
            '<w:between w:val="nil"/></w:pBdr><w:ind w:firstLine="200"/><w:jc w:val="both"/></w:pPr>')


def para_xml(text, first=False):
    ppr = BODY_PPR.replace('<w:ind w:firstLine="200"/>', "") if first else BODY_PPR
    return f"<w:p {NSDECL}>{ppr}{rich_runs(text, sz=20)}</w:p>"


def note_xml(text):
    return (f'<w:p {NSDECL}><w:pPr><w:jc w:val="both"/></w:pPr>'
            f'{run("AUTHOR NOTE: " + text, sz=18, italic=True, color="B03A2E", highlight="yellow")}</w:p>')


_bm = [100]


def bookmark(name, inner):
    _bm[0] += 1
    i = _bm[0]
    return f'<w:bookmarkStart w:id="{i}" w:name="{name}"/>{inner}<w:bookmarkEnd w:id="{i}"/>'


HFONT = "Helvetica Neue"


def heading1_xml(label, text, bm=None):
    rp = dict(sz=18, bold=True, color="00629B", font=HFONT)
    inner = (run(label, **rp) + run("\u2003", sz=18, bold=True, color="00629B", font="MS Gothic") if label else "") \
        + run(text.upper(), **rp)
    if bm:
        inner = bookmark(bm, inner)
    return (f'<w:p {NSDECL}><w:pPr><w:keepNext/><w:spacing w:before="240"/><w:rPr>{rpr(**rp)[7:-8]}</w:rPr></w:pPr>'
            f"{inner}</w:p>")


def heading2_xml(label, text):
    rp = dict(sz=18, bold=True, italic=True, color="58595B", font=HFONT)
    return (f'<w:p {NSDECL}><w:pPr><w:keepNext/><w:spacing w:before="200"/></w:pPr>'
            f'{run(label, **rp)}{run(chr(8194), sz=18, bold=True, italic=True, color="58595B", font="MS Gothic")}'
            f"{run(text.upper(), **rp)}</w:p>")


# ============================================================================ equations (OMML)
def mr(t, plain=False):
    sty = '<m:rPr><m:sty m:val="p"/></m:rPr>' if plain else ""
    return f'<m:r>{sty}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/><w:sz w:val="20"/></w:rPr><m:t xml:space="preserve">{esc(t)}</m:t></m:r>'


def sub(b, s):
    return f"<m:sSub><m:e>{b}</m:e><m:sub>{s}</m:sub></m:sSub>"


def subsup(b, s, p):
    return f"<m:sSubSup><m:e>{b}</m:e><m:sub>{s}</m:sub><m:sup>{p}</m:sup></m:sSubSup>"


def frac(n, d):
    return f"<m:f><m:num>{n}</m:num><m:den>{d}</m:den></m:f>"


def sqrt(x):
    return f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{x}</m:e></m:rad>'


def paren(x, l="(", r=")"):
    return f'<m:d><m:dPr><m:begChr m:val="{l}"/><m:endChr m:val="{r}"/></m:dPr><m:e>{x}</m:e></m:d>'


def nsum(lo, hi, body):
    lo_x = f"<m:sub>{lo}</m:sub>" if lo else "<m:sub/>"
    hi_x = f"<m:sup>{hi}</m:sup>" if hi else "<m:sup/>"
    hide = "" if hi else '<m:supHide m:val="1"/>'
    return (f'<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/>{hide}</m:naryPr>'
            f"{lo_x}{hi_x}<m:e>{body}</m:e></m:nary>")


def acc(x, ch="̂"):
    return f'<m:acc><m:accPr><m:chr m:val="{ch}"/></m:accPr><m:e>{x}</m:e></m:acc>'


def R(*parts):
    return "".join(parts)


EQUATIONS = {
    "utilisation": R(mr("U"), mr("="), frac(nsum(mr("t"), "", R(sub(mr("c"), mr("used", True)), paren(mr("t")), mr("Δ"), mr("t"))),
                                            nsum(mr("t"), "", R(sub(mr("c"), mr("total", True)), paren(mr("t")), mr("Δ"), mr("t"))))),
    "zscore": R(sub(mr("z"), mr("t")), mr("="), frac(R(sub(mr("x"), mr("t")), mr("−"), sub(mr("μ"), R(mr("t"), mr("−1")))),
                                                  sub(mr("σ"), R(mr("t"), mr("−1"))))),
    "health": R(sub(mr("H"), mr("k")), mr("=1−"), nsum(R(mr("i"), mr("=1")), mr("5"), R(sub(mr("w"), mr("i")), sub(mr("a"), mr("i,k"))))),
    "daly": R(sup_star := subsup(mr("τ"), "", mr("*")) if False else R(f"<m:sSup><m:e>{mr('τ')}</m:e><m:sup>{mr('*')}</m:sup></m:sSup>"),
              mr("="), sqrt(R(mr("2"), mr("C"), mr("M"))),
              paren(R(mr("1+"), frac(mr("1"), mr("3")), sqrt(frac(mr("C"), R(mr("2"), mr("M")))), mr("+"), frac(mr("1"), mr("9")),
                      frac(mr("C"), R(mr("2"), mr("M")))), "[", "]"), mr("−"), mr("C")),
    "lostwork": R(sub(mr("W"), mr("lost", True)), mr("≈"), frac(mr("τ"), mr("2")), mr("+"), mr("C")),
    "mtbf": R(acc(mr("M")), mr("="), frac(R(sub(mr("M"), mr("0")), sub(mr("n"), mr("0")), mr("+"), sub(mr("T"), mr("up", True))),
                                          R(sub(mr("n"), mr("0")), mr("+"), sub(mr("N"), mr("f"))))),
    "placement": R(sub(mr("J"), mr("k")), mr("="), mr("α"), sub(mr("L"), mr("k")), mr("+"), mr("β"),
                   paren(R(mr("1−"), sub(mr("H"), mr("k")))), mr("+"), mr("γ"), sub(mr("T"), mr("k"))),
    "reliability": R(sub(mr("R"), mr("k")), mr("="), nsum(mr("j"), "", R(sub(mr("w"), mr("j")), sub(mr("s"), mr("j,k"))))),
    "availability": R(mr("A"), mr("="), frac(mr("MTBF", True), R(mr("MTBF", True), mr("+"), mr("MTTR", True)))),
    "trec": R(sub(mr("T"), mr("rec", True)), mr("="), sub(mr("t"), mr("resume", True)), mr("−"), sub(mr("t"), mr("fault", True))),
    "overhead": R(mr("O"), mr("="), frac(R(subsup(mr("T"), mr("clean", True), mr("sys", True)), mr("−"),
                                           subsup(mr("T"), mr("clean", True), mr("B1", True))),
                                         subsup(mr("T"), mr("clean", True), mr("B1", True)))),
    "benefit": R(mr("Δ"), mr("B"), mr("="), sub(mr("N"), mr("f")),
                 paren(R(sub(mr("D"), mr("base", True)), mr("−"), sub(mr("D"), mr("rmc", True)))),
                 sub(mr("C"), mr("d")), mr("−"), sub(mr("C"), mr("extra", True))),
}


def equation_xml(key, num):
    math = EQUATIONS[key]
    center, right = COL_TWIPS // 2, COL_TWIPS
    return (f'<w:p {NSDECL}><w:pPr><w:tabs><w:tab w:val="center" w:pos="{center}"/><w:tab w:val="right" w:pos="{right}"/>'
            f'</w:tabs><w:spacing w:before="120" w:after="120"/></w:pPr><w:r><w:tab/></w:r><m:oMath>{math}</m:oMath>'
            f'<w:r><w:tab/></w:r>{run(f"({num})", sz=20)}</w:p>')


# ============================================================================ figures
class Media:
    def __init__(self, rels_root):
        self.rels = rels_root
        self.n = 0

    def add(self, src, workdir):
        self.n += 1
        name = f"rmc_fig{self.n:02d}.png"
        shutil.copy(src, os.path.join(workdir, "word", "media", name))
        rid = f"rIdRmc{self.n}"
        etree.SubElement(self.rels, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                         Id=rid, Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                         Target=f"media/{name}")
        return rid


def figure_xml(rid, src, wide, docpr_id, max_h_in=3.6):
    with Image.open(src) as im:
        w_px, h_px = im.size
    width_emu = (WIDE_TWIPS if wide else COL_TWIPS) * EMU_PER_TWIP
    height_emu = int(width_emu * h_px / w_px)
    max_h = int(max_h_in * 914400)
    if height_emu > max_h:
        width_emu = int(width_emu * max_h / height_emu)
        height_emu = max_h
    return (f'<w:p {NSDECL}><w:pPr><w:keepNext/><w:spacing w:before="120"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{width_emu}" cy="{height_emu}"/>'
            f'<wp:docPr id="{docpr_id}" name="Figure {docpr_id}"/><wp:cNvGraphicFramePr>'
            f'<a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="{docpr_id}" name="{os.path.basename(src)}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            f"</wp:inline></w:drawing></w:r></w:p>")


def fig_caption_xml(num, caption, bm):
    lab = run(f"FIGURE {num}.", sz=14, bold=True, color="00629B", font=HFONT) + run("\u2003", sz=14, font="MS Gothic")
    return (f'<w:p {NSDECL}><w:pPr><w:spacing w:before="60" w:after="160"/><w:jc w:val="both"/></w:pPr>'
            f'{bookmark(bm, lab)}{rich_runs(" " + caption, sz=14, font=HFONT)}</w:p>')


# ============================================================================ tables
def table_xml(rows, widths_pct, wide, numbers):
    total = WIDE_TWIPS if wide else COL_TWIPS
    ncol = max(len(r) for r in rows)
    bad = [r for r in rows if len(r) != len(rows[0])]
    if bad:   # a "|" inside a cell would silently shift the columns
        raise SystemExit(f"table row has {len(bad[0])} cells, header has {len(rows[0])}: {bad[0][:3]}")
    pct = widths_pct if widths_pct and len(widths_pct) == ncol else [100 / ncol] * ncol
    s = sum(pct)
    widths = [int(total * p / s) for p in pct]
    widths[-1] = total - sum(widths[:-1])
    sz = 14
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = [f'<w:tbl {NSDECL}><w:tblPr><w:tblW w:w="{total}" w:type="dxa"/><w:jc w:val="center"/>'
           '<w:tblBorders><w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
           '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
           '<w:insideH w:val="single" w:sz="2" w:space="0" w:color="BFBFBF"/></w:tblBorders>'
           '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="57" w:type="dxa"/><w:right w:w="57" w:type="dxa"/>'
           '</w:tblCellMar></w:tblPr>' + f"<w:tblGrid>{grid}</w:tblGrid>"]
    for ri, r in enumerate(rows):
        hdr = ri == 0
        trpr = "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if hdr else "<w:trPr><w:cantSplit/></w:trPr>"
        cells = []
        # keep-with-next on every row but the last chains caption and rows together, so no table splits across pages
        keep = "<w:keepNext/>" if ri < len(rows) - 1 else ""
        for ci in range(ncol):
            txt = numbers.resolve(r[ci]) if ci < len(r) else ""
            border = '<w:tcBorders><w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/></w:tcBorders>' if hdr else ""
            shade = '<w:shd w:val="clear" w:color="auto" w:fill="E3F0F8"/>' if hdr else ""
            cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[ci]}" w:type="dxa"/>{border}{shade}</w:tcPr>'
                         f'<w:p><w:pPr>{keep}<w:spacing w:before="20" w:after="20"/></w:pPr>'
                         f'{rich_runs(txt, sz=sz, bold=hdr)}</w:p></w:tc>')
        out.append(f"<w:tr>{trpr}{''.join(cells)}</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def table_caption_xml(num, caption, bm):
    return (f'<w:p {NSDECL}><w:pPr><w:keepNext/><w:spacing w:before="160"/><w:jc w:val="center"/></w:pPr>'
            f'{bookmark(bm, run(f"TABLE {num}", sz=16, smallcaps=True))}</w:p>'
            f'<w:p {NSDECL}><w:pPr><w:keepNext/><w:spacing w:after="60"/><w:jc w:val="center"/></w:pPr>'
            f'{rich_runs(caption, sz=16, smallcaps=True)}</w:p>')


SECT_TMPL = ('<w:p {ns}><w:pPr><w:sectPr><w:type w:val="continuous"/><w:pgSz w:w="11906" w:h="16838" w:code="9"/>'
             '<w:pgMar w:top="720" w:right="1440" w:bottom="720" w:left="1440" w:header="709" w:footer="709" w:gutter="0"/>'
             '<w:pgBorders w:offsetFrom="page"><w:top w:val="basicWhiteDashes" w:sz="6" w:space="24" w:color="auto"/>'
             '<w:left w:val="basicWhiteDashes" w:sz="6" w:space="24" w:color="auto"/>'
             '<w:bottom w:val="basicWhiteDashes" w:sz="6" w:space="24" w:color="auto"/>'
             '<w:right w:val="basicWhiteDashes" w:sz="6" w:space="24" w:color="auto"/></w:pgBorders>'
             '{cols}<w:docGrid w:linePitch="360"/></w:sectPr></w:pPr></w:p>')


def section_break(cols):
    c = '<w:cols w:num="2" w:space="708"/>' if cols == 2 else '<w:cols w:space="708"/>'
    return SECT_TMPL.format(ns=NSDECL, cols=c)


# ============================================================================ references
def initials(name):
    parts = name.replace(".", ". ").split()
    if len(parts) == 1:
        return parts[0]
    first = " ".join(p[0] + "." for p in parts[:-1] if p[0].isalpha())
    return f"{first} {parts[-1]}"


def initials_cr(given, family):
    """IEEE form from Crossref name parts: 'Nian-Feng', 'Tzeng' -> 'N.-F. Tzeng'; keeps 'van Dongen'."""
    out = []
    for word in given.replace(".", ". ").split():
        if word[0].isalpha():
            out.append("-".join(p[0] + "." for p in word.split("-") if p))
    return (" ".join(out) + " " + family).strip()


def ieee_ref(r):
    if r.get("authors_cr"):
        a = [initials_cr(g, f) for g, f in r["authors_cr"]]
    else:
        a = [initials(x) for x in r["authors"]]
    if len(a) > 6:
        auth = f"{a[0]} et al."
    elif len(a) > 1:
        auth = ", ".join(a[:-1]) + (", and " if len(a) > 2 else " and ") + a[-1]
    else:
        auth = a[0] if a else "Anonymous"
    title = r["title"].rstrip(".")
    venue = r.get("venue") or ""
    is_conf = (r.get("type") == "conference") or any(w in venue for w in ("Proceedings", "Proc.", "Conference",
                                                                           "Symposium", "Workshop", "European Conference"))
    if "VLDB Endowment" in venue or "Proceedings of the ACM on" in venue:
        is_conf = False
    bits = []
    if r.get("volume"):
        bits.append(f"vol. {r['volume']}")
    if r.get("issue"):
        bits.append(f"no. {r['issue']}")
    if r.get("first_page"):
        fp, lp = r["first_page"], r.get("last_page")
        if lp and lp != fp:
            bits.append(f"pp. {fp}–{lp}")
        elif fp:
            bits.append(f"Art. no. {fp}" if not str(fp).isdigit() or int(fp) > 9999 else f"p. {fp}")
    bits.append(str(r["year"]))
    tail = ", ".join(bits)
    doi = f", doi: {r['doi']}." if r.get("doi") else "."
    if is_conf:
        return auth, f", “{title},” in ", f"{venue}", f", {tail}{doi}"
    return auth, f", “{title},” ", venue, f", {tail}{doi}"


def reference_xml(r):
    auth, mid_, venue, tail = ieee_ref(r)
    return (f'<w:p {NSDECL}><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="22"/></w:numPr><w:jc w:val="both"/></w:pPr>'
            f'{run(auth + mid_, sz=16)}{run(venue, sz=16, italic=True)}{run(tail, sz=16)}</w:p>')


# ============================================================================ main build
def word_count(text):
    text = re.sub(r"\[\[.*?\]\]", " ", text)
    text = re.sub(r"\[\d+\]", " ", text)
    return len(re.findall(r"[A-Za-z0-9][\w'’\-./]*", text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=os.path.join(HERE, "3_Consolidated_Template.docx"))   # or pass --template
    ap.add_argument("--out", default=os.path.join(HERE, "RMC-Spark_Manuscript.docx"))
    a = ap.parse_args()

    refs_list = json.load(open(os.path.join(HERE, "refs", "refs_keyed.json"), encoding="utf-8"))
    refs = {r["key"]: r for r in refs_list}
    refs["daly2004higher"].update(year=2006, volume="22", issue="3", first_page="303", last_page="312")
    blocks = parse_sources()
    nums = Numbers(blocks, refs)

    work = tempfile.mkdtemp(prefix="rmcdocx_")
    with zipfile.ZipFile(a.template) as z:
        z.extractall(work)
    doc_path = os.path.join(work, "word", "document.xml")
    tree = etree.parse(doc_path)
    body = tree.getroot().find(W + "body")
    rels_path = os.path.join(work, "word", "_rels", "document.xml.rels")
    rels = etree.parse(rels_path)
    media = Media(rels.getroot())

    def el(xml):
        wrapper = etree.fromstring(f"<wrap {NSDECL}>{xml}</wrap>")
        return list(wrapper)

    def texts(p):
        return [t for t in p.iter(W + "t")]

    children = list(body)
    idx_intro = next(i for i, e in enumerate(children) if "".join(e.itertext()).strip().startswith("I.") and "INTRODUCTION" in "".join(e.itertext()))
    idx_bio = next(i for i, e in enumerate(children) if "Dr. M. Rajasekhara Babu" in "".join(e.itertext()) and "received" in "".join(e.itertext()))
    idx_second_bio = next(i for i, e in enumerate(children) if "SECOND B. AUTHOR" in "".join(e.itertext()))
    idx_sect_end = next(i for i in range(idx_second_bio, len(children))
                        if children[i].find(".//" + W + "sectPr") is not None)

    # -------------------------------------------------- front matter blocks
    title = next(b["text"] for b in blocks if b["t"] == "title")
    abstract = next(b["text"] for b in blocks if b["t"] == "abstract")
    keywords = next(b["text"] for b in blocks if b["t"] == "keywords")

    for t in children[0].iter(W + "t"):
        if t.text and t.text.startswith("Team ID"):
            t.text = f"Team ID: {TEAM_ID}"
            r = t.getparent()
            rp = r.find(W + "rPr")
            if rp is None:
                rp = etree.SubElement(r, W + "rPr")
                r.remove(rp)
                r.insert(0, rp)
            for tag in ("sz", "szCs"):
                for e in rp.findall(W + tag):
                    rp.remove(e)
                e = etree.SubElement(rp, W + tag)
                e.set(W + "val", "14")
    ts = texts(children[1])
    ts[0].text = f"On “{title}”"
    for t in ts[1:]:
        t.text = ""
    # paper title block
    p_title = next(e for e in children if "".join(e.itertext()) == "<TITLE OF THE PAPER>")
    for i, t in enumerate(texts(p_title)):
        t.text = title if i == 0 else ""
    bs = etree.SubElement(p_title, W + "bookmarkStart")   # Index entry for the title/abstract page
    bs.set(W + "id", "9990")
    bs.set(W + "name", "sec_front")
    be = etree.SubElement(p_title, W + "bookmarkEnd")
    be.set(W + "id", "9990")
    p_auth = next(e for e in children if "".join(e.itertext()).startswith("Dr. M Rajasekhara Babu1"))
    rep = {", Second B. Author": f", [[Student name]] ({REGS[0]})", ", Third C. Author": f", [[Student name]] ({REGS[1]})",
           "Fourth D. Author": f"[[Student name]] ({REGS[2]})", ", Fifth E. Author": f", [[Student name]] ({REGS[3]})"}
    for t in texts(p_auth):
        if t.text in rep:
            t.text = rep[t.text]
    p_mail = next(e for e in children if "".join(e.itertext()).startswith("1mrajasekharababu"))
    mt = texts(p_mail)
    new_vals = {"Second B. Author": f"{REGS[0]}", "Third C. Author": f"{REGS[1]}", "Fourth D. Author": f"{REGS[2]}",
                "Fifth E": f"{REGS[3]}", ". Author": "", " Vit email, ": " [VIT e-mail], ", " Vit email": " [VIT e-mail]"}
    seen4 = 0
    for t in mt:
        if t.text == "4":
            seen4 += 1
            if seen4 == 2:
                t.text = "5"
        elif t.text in new_vals:
            t.text = new_vals[t.text]

    # author line: one name per slot, never broken mid-name (professor, then two students per line)
    def set_runs(p, xml):
        for ch in [c for c in p if c.tag != W + "pPr"]:
            p.remove(ch)
        for ch in etree.fromstring(f'<w:p {NSDECL}>{xml}</w:p>'):
            p.append(ch)

    ak = dict(sz=20, bold=True, font=HFONT)
    stud = [run("[[Student name]]", highlight="yellow", **ak) + run(f" ({r})", **ak) + run(str(i + 2), va="superscript", **ak)
            for i, r in enumerate(REGS)]
    set_runs(p_auth, run("Dr. M Rajasekhara Babu", **ak) + run("1", va="superscript", **ak) + "<w:r><w:br/></w:r>"
             + stud[0] + run(", ", **ak) + stud[1] + "<w:r><w:br/></w:r>" + stud[2] + run(", ", **ak) + stud[3])
    # affiliation, e-mail and corresponding-author lines: the template's 0.75 line spacing makes them overlap
    p_aff = p_auth.getnext()
    for p in (p_auth, p_aff, p_mail, p_mail.getnext()):
        ppr = p.find(W + "pPr")
        sp = ppr.find(W + "spacing")
        if sp is None:
            sp = etree.Element(W + "spacing")
            nxt = ppr.find(W + "ind") if ppr.find(W + "ind") is not None else ppr.find(W + "jc")
            ppr.insert(list(ppr).index(nxt) if nxt is not None else 0, sp)
        for k in list(sp.attrib):
            del sp.attrib[k]
        sp.set(W + "before", "0" if p is not p_auth else "120")
        sp.set(W + "after", {id(p_auth): "120", id(p_aff): "20", id(p_mail): "60"}.get(id(p), "120"))
        sp.set(W + "line", "264" if p is p_auth else "240")
        sp.set(W + "lineRule", "auto")
        if p is not p_auth:
            for e in p.iter(W + "sz", W + "szCs"):
                e.set(W + "val", "16")
    p_abs = next(e for e in children if "".join(e.itertext()).startswith("ABSTRACT"))
    at = texts(p_abs)
    at[1].text = " " + abstract
    for t in at[2:]:
        t.text = ""
    p_kw = next(e for e in children if "".join(e.itertext()).startswith("INDEX TERMS"))
    kt = texts(p_kw)
    kt[1].text = " " + keywords
    kppr = p_kw.find(W + "pPr")
    for e in kppr.findall(W + "ind"):   # template right indent made the keywords wrap early
        kppr.remove(e)
    if kppr.find(W + "jc") is None:
        jc = etree.Element(W + "jc")
        jc.set(W + "val", "both")
        kppr.insert(list(kppr).index(kppr.find(W + "rPr")), jc)
    for t in kt[2:]:
        t.text = ""

    # -------------------------------------------------- body generation
    new = []
    sec_no = 0
    sub_no = 0
    cur_cols = 2
    docpr = 5000
    word_by_sec = OrderedDict()
    sec_titles = OrderedDict()
    cur_sec_key = 0
    word_by_sec[0] = word_count(abstract) + word_count(keywords)
    kw_words = word_count(keywords)
    first_para = True
    fig_entries, tab_entries = [], []

    def ensure_cols(n):
        nonlocal cur_cols
        if cur_cols != n:
            new.append(section_break(cur_cols))
            cur_cols = n

    for b in blocks:
        t = b["t"]
        if t in ("title", "abstract", "keywords"):
            continue
        if t in ("section", "unnumbered"):
            ensure_cols(2)
            if t == "section":
                sec_no += 1
                sub_no = 0
                cur_sec_key = sec_no
                sec_titles[sec_no] = b["text"]
                new.append(heading1_xml(f"{ROMAN[sec_no - 1]}.", b["text"], bm=f"sec_{sec_no}"))
            else:
                sub_no = 0
                name = b["text"]
                cur_sec_key = {"Executive Summary": 0, "Appendix": "appendix"}.get(name, "other")
                new.append(heading1_xml("", name, bm={"Appendix": "sec_appendix"}.get(name)))
            word_by_sec.setdefault(cur_sec_key, 0)
            first_para = True
        elif t == "sub":
            ensure_cols(2)
            label = chr(ord("A") + sub_no) + "."
            sub_no += 1
            new.append(heading2_xml(label, b["text"]))
            first_para = True
        elif t == "para":
            ensure_cols(2)
            txt = nums.resolve(b["text"])
            new.append(para_xml(txt, first=first_para))
            word_by_sec[cur_sec_key] = word_by_sec.get(cur_sec_key, 0) + word_count(txt)
            first_para = False
        elif t == "note":
            ensure_cols(2)
            new.append(note_xml(b["text"]))
        elif t == "equation":
            ensure_cols(2)
            new.append(equation_xml(b["key"], nums.eq[b["key"]]))
        elif t == "figure":
            n = nums.fig[b["key"]]
            assert b["file"].startswith(f"Fig {n:02d} "), (n, b["file"])
            src = os.path.join(HERE, "Diagrams", b["file"] + ".png")
            ensure_cols(1 if b["wide"] else 2)
            rid = media.add(src, work)
            docpr += 1
            new.append(figure_xml(rid, src, b["wide"], docpr))
            cap = nums.resolve(b["caption"])
            new.append(fig_caption_xml(n, cap, f"fig_{n}"))
            word_by_sec[cur_sec_key] = word_by_sec.get(cur_sec_key, 0) + word_count(cap)
            fig_entries.append((n, b["file"].split(" ", 2)[2]))
            ensure_cols(2)
        elif t == "table":
            n = nums.tab[b["key"]]
            ensure_cols(1 if b["wide"] else 2)
            new.append(table_caption_xml(n, nums.resolve(b["caption"]), f"tab_{n}"))
            new.append(table_xml(b["rows"], b["widths"], b["wide"], nums))
            new.append(f'<w:p {NSDECL}><w:pPr><w:spacing w:after="60"/></w:pPr></w:p>')
            tab_entries.append((n, b["caption"]))
            ensure_cols(2)
    ensure_cols(2)

    # references
    new.append(heading1_xml("", "References", bm="sec_refs"))
    for k in nums.cite:
        new.append(reference_xml(refs[k]))

    # -------------------------------------------------- author biographies: photo left, text right
    faculty_bio = children[idx_bio:idx_second_bio]
    blip = faculty_bio[0].find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
    photo_rid = blip.get(f"{{{R_NS}}}embed")
    bio_paras = []                       # the professor's text, runs copied without the anchored picture
    for p in faculty_bio:
        rs = [copy.deepcopy(r) for r in p.findall(W + "r") if r.find(".//" + W + "drawing") is None]
        for r in rs:
            for lb in r.findall(W + "lastRenderedPageBreak"):
                r.remove(lb)
        if "".join(t.text or "" for r in rs for t in r.iter(W + "t")).strip():
            bio_paras.append(rs)
    PHOTO_W, TEXT_W = 1560, COL_TWIPS - 1560
    ext = faculty_bio[0].find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
    PHOTO_CX, PHOTO_CY = int(ext.get("cx")), int(ext.get("cy"))   # keep the template photo's size and aspect

    def bio_table(left_xml, right_paras_xml, framed):
        border = ('<w:tcBorders><w:top w:val="single" w:sz="4" w:color="808080"/><w:left w:val="single" w:sz="4" w:color="808080"/>'
                  '<w:bottom w:val="single" w:sz="4" w:color="808080"/><w:right w:val="single" w:sz="4" w:color="808080"/></w:tcBorders>'
                  if framed else "")
        return (f'<w:tbl {NSDECL}><w:tblPr><w:tblW w:w="{COL_TWIPS}" w:type="dxa"/>'
                '<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/>'
                '<w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders><w:tblLayout w:type="fixed"/>'
                '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>'
                f'<w:tblGrid><w:gridCol w:w="{PHOTO_W}"/><w:gridCol w:w="{TEXT_W}"/></w:tblGrid>'
                '<w:tr><w:trPr><w:cantSplit/></w:trPr>'
                f'<w:tc><w:tcPr><w:tcW w:w="{PHOTO_W}" w:type="dxa"/>{border}<w:vAlign w:val="top"/></w:tcPr>{left_xml}</w:tc>'
                f'<w:tc><w:tcPr><w:tcW w:w="{TEXT_W}" w:type="dxa"/></w:tcPr>{right_paras_xml}</w:tc></w:tr></w:tbl>'
                # thin spacer (exact 1 pt line) so the professor and all four students fit on one page
                f'<w:p {NSDECL}><w:pPr><w:spacing w:before="0" w:after="120" w:line="20" w:lineRule="exact"/></w:pPr></w:p>')

    photo_xml = (f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
                 f'<wp:extent cx="{PHOTO_CX}" cy="{PHOTO_CY}"/><wp:docPr id="7001" name="Author photo"/>'
                 '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                 '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                 '<pic:nvPicPr><pic:cNvPr id="7001" name="Author photo"/><pic:cNvPicPr/></pic:nvPicPr>'
                 f'<pic:blipFill><a:blip r:embed="{photo_rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                 f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{PHOTO_CX}" cy="{PHOTO_CY}"/></a:xfrm>'
                 '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
                 '</wp:inline></w:drawing></w:r></w:p>')
    prof_text = "".join(
        f'<w:p {NSDECL}><w:pPr><w:spacing w:after="60"/><w:jc w:val="both"/></w:pPr>'
        + "".join(etree.tostring(r).decode() for r in rs) + "</w:p>" for rs in bio_paras)
    bios = [f'<w:p {NSDECL}><w:pPr><w:spacing w:before="0" w:after="240"/></w:pPr></w:p>',   # gap after the references
            bio_table(photo_xml, prof_text, framed=False)]
    # suggested research interests (members should adjust); the sections come from OWNER, so they always match
    # the Contributions table. Kept short so the professor and all four students fit in one column.
    INTERESTS = {"26MML0054": "anomaly detection and AIOps",
                 "26MML0006": "big data engineering and Spark performance",
                 "26MML0047": "cloud security and data governance",
                 "26MML0015": "distributed systems and fault tolerance"}

    def wrote(reg):
        secs = [ROMAN[k - 1] for k in sorted(k for k, v in OWNER.items() if v == reg and k)]
        parts = (["the abstract"] if OWNER.get(0) == reg else []) + [f"Sections {', '.join(secs[:-1])} and {secs[-1]}"]
        if APPENDIX_OWNER == reg:
            parts.append("the Appendix")
        lead = "Team point of contact; wrote " if reg == "26MML0015" else "Wrote "
        return lead + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]) + "."

    for reg in REGS:
        frame = (f'<w:p><w:pPr><w:spacing w:before="480" w:after="480"/><w:jc w:val="center"/></w:pPr>'
                 f'{run("Photo", sz=14, color="808080")}</w:p>')
        text = (f'<w:p {NSDECL}><w:pPr><w:jc w:val="both"/></w:pPr>'
                f'{run("[[STUDENT NAME]] ", sz=16, bold=True, font=HFONT, highlight="yellow")}'
                f'{run(f"(Reg. No. {reg}) is a postgraduate student in the School of Computer Science and Engineering, VIT, Vellore, India. ", sz=16)}'
                f'{run(f"Research interests: {INTERESTS[reg]}. {wrote(reg)}", sz=16)}</w:p>')
        bios.append(bio_table(frame, text, framed=True))
    # keep-with-next on every bio paragraph: the professor and the four students move as one block into the
    # next column instead of splitting (a hard column break breaks Word's balancing of the final sections)
    bios = [b.replace("<w:pPr>", "<w:pPr><w:keepNext/>") for b in bios]

    # -------------------------------------------------- splice into body
    keep_before = children[:idx_intro]
    tail = children[idx_sect_end:]
    for c in list(body):
        body.remove(c)
    for c in keep_before:
        body.append(c)
    for x in new:
        for e in el(x):
            body.append(e)
    for x in bios:
        for e in el(x):
            body.append(e)
    # The template ends with empty paragraphs and two extra continuous sections after the bios; with the bios
    # filling the right column Word pushes those empty sections onto a blank last page. Drop them and let the
    # bios' own two-column section properties close the document instead.
    last_sect = None
    for c in tail:
        if c.tag == W + "sectPr":
            if last_sect is not None:
                c = copy.deepcopy(last_sect)
            body.append(c)
            continue
        sp = c.find(".//" + W + "sectPr")
        if (c.tag == W + "p" and not "".join(c.itertext()).strip() and c.find(".//" + W + "drawing") is None
                and c.find(".//" + W + "br") is None):
            if sp is not None and last_sect is None:
                last_sect = sp       # properties of the section that holds the references and bios
            continue
        body.append(c)

    # -------------------------------------------------- remove empty spacer paragraphs after the list of tables
    tbls = [c for c in body if c.tag == W + "tbl"]
    nxt = tbls[2].getnext()
    while nxt is not None and nxt.tag == W + "p" and not "".join(nxt.itertext()).strip():
        after = nxt.getnext()
        if (nxt.find(".//" + W + "br") is not None or nxt.find(".//" + W + "sectPr") is not None
                or nxt.find(".//" + W + "drawing") is not None or nxt.find(".//" + W + "pict") is not None):
            break
        body.remove(nxt)
        nxt = after

    # -------------------------------------------------- front tables
    tables = [c for c in body if c.tag == W + "tbl"]
    t_index, t_figs, t_tabs, t_contrib, t_cons = tables[0], tables[1], tables[2], tables[3], tables[4]

    def cell_set(tc, text, field=None, left=False):
        p = tc.find(W + "p")
        ppr = p.find(W + "pPr")
        if ppr is not None and ppr.find(W + "numPr") is not None and not field:
            text = ""   # the template auto-numbers this column
        if left and ppr is not None:
            for jc in ppr.findall(W + "jc"):
                ppr.remove(jc)
            jc = etree.Element(W + "jc")
            jc.set(W + "val", "left")
            later = ("textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
                     "sectPr", "pPrChange")
            pos = next((i for i, ch in enumerate(ppr) if etree.QName(ch).localname in later), len(ppr))
            ppr.insert(pos, jc)
        for r in p.findall(W + "r"):
            p.remove(r)
        for f in p.findall(W + "fldSimple"):
            p.remove(f)
        if field:
            fs = etree.SubElement(p, W + "fldSimple")
            fs.set(W + "instr", f" PAGEREF {field} \\h ")
            r = etree.SubElement(fs, W + "r")
            etree.SubElement(r, W + "t").text = "#"
        else:
            r = etree.SubElement(p, W + "r")
            rp = etree.SubElement(r, W + "rPr")
            f = etree.SubElement(rp, W + "rFonts")
            for k in ("ascii", "hAnsi", "cs"):
                f.set(W + k, "Times New Roman")
            tt = etree.SubElement(r, W + "t")
            tt.text = text
            tt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    def fit_rows(tbl, n_body):
        rows = tbl.findall(W + "tr")
        body_rows = rows[1:]
        while len(body_rows) < n_body:
            c = copy.deepcopy(body_rows[-1])
            tbl.append(c)
            body_rows.append(c)
        for r in body_rows[n_body:]:
            tbl.remove(r)
        return body_rows[:n_body]

    # Index: Abstract, 22 sections, References, Appendix
    entries = [("", "Executive Summary and Abstract", "sec_front")]  # page of the paper start ~ before sec 1
    entries += [(str(i), f"{ROMAN[i - 1]}. {t}", f"sec_{i}") for i, t in sec_titles.items()]
    entries += [("", "Appendix", "sec_appendix"), ("", "References", "sec_refs")]   # document order
    for row, (sl, name, bm) in zip(fit_rows(t_index, len(entries)), entries):
        tcs = row.findall(W + "tc")
        cell_set(tcs[0], sl)
        cell_set(tcs[1], name, left=True)
        cell_set(tcs[2], "", field=bm)
    for row, (n, name) in zip(fit_rows(t_figs, len(fig_entries)), fig_entries):
        tcs = row.findall(W + "tc")
        cell_set(tcs[0], str(n))
        cell_set(tcs[1], name, left=True)
        cell_set(tcs[2], "", field=f"fig_{n}")
    for row, (n, name) in zip(fit_rows(t_tabs, len(tab_entries)), tab_entries):
        tcs = row.findall(W + "tc")
        cell_set(tcs[0], str(n))
        cell_set(tcs[1], name, left=True)
        cell_set(tcs[2], "", field=f"tab_{n}")

    # Contributions
    contrib = [("", "Executive Summary, Abstract and Keywords", OWNER[0], word_by_sec.get(0, 0))]
    for i, t in sec_titles.items():
        contrib.append((str(i), f"{ROMAN[i - 1]}. {t}", OWNER[i], word_by_sec.get(i, 0)))
    ref_words = sum(word_count("".join(ieee_ref(refs[k]))) for k in nums.cite)
    contrib.append(("", f"References ({len(nums.cite)})", REFERENCES_OWNER, ref_words))
    contrib.append(("", "Appendix and Data Availability", APPENDIX_OWNER,
                    word_by_sec.get("appendix", 0) + word_by_sec.get("other", 0)))
    for row, (sl, name, reg, wc) in zip(fit_rows(t_contrib, len(contrib)), contrib):
        tcs = row.findall(W + "tc")
        cell_set(tcs[0], sl)
        cell_set(tcs[1], name, left=True)
        cell_set(tcs[2], reg if not name.startswith("References") else "All members")
        cell_set(tcs[3], str(wc) if not name.startswith("References") else "not counted")
    totals = OrderedDict((r, 0) for r in REGS)
    for _, name, reg, wc in contrib:
        if not name.startswith("References"):
            totals[reg] += wc
    cons_rows = t_cons.findall(W + "tr")
    for row, reg in zip(cons_rows[2:6], REGS):
        tcs = row.findall(W + "tc")
        cell_set(tcs[1], reg)
        cell_set(tcs[2], str(totals[reg]))
    tcs = cons_rows[6].findall(W + "tc")
    cell_set(tcs[-1], str(sum(totals.values())))

    # -------------------------------------------------- front-matter layout: one look for every list table
    def el(parent, tag, before=(), **attrs):
        e = parent.find(W + tag)
        if e is None:
            e = etree.Element(W + tag)
            pos = next((i for i, ch in enumerate(parent) if etree.QName(ch).localname in before), len(parent))
            parent.insert(pos, e)
        for k, v in attrs.items():
            e.set(W + k, v)
        return e

    TPR_AFTER = ("tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription")
    def normalise(tbl, widths=None, pad="40"):
        tpr = tbl.find(W + "tblPr")
        for e in tpr.findall(W + "tblInd"):
            tpr.remove(e)
        el(tpr, "jc", before=("tblCellSpacing", "tblInd", "tblBorders", "shd") + TPR_AFTER, val="center")
        if widths:
            el(tpr, "tblW", before=("jc",), w=str(sum(widths)), type="dxa")
            el(tpr, "tblLayout", before=("tblCellMar", "tblLook", "tblCaption", "tblDescription"), type="fixed")
            grid = tbl.find(W + "tblGrid")
            for g, wd in zip(grid.findall(W + "gridCol"), widths):
                g.set(W + "w", str(wd))
        for tr in tbl.findall(W + "tr"):
            trpr = tr.find(W + "trPr")
            if trpr is not None:
                for e in trpr.findall(W + "trHeight") + trpr.findall(W + "jc"):
                    trpr.remove(e)
            tcs = tr.findall(W + "tc")
            for ci, tc in enumerate(tcs):
                tcpr = tc.find(W + "tcPr")
                if widths and len(tcs) == len(widths):
                    el(tcpr, "tcW", before=("gridSpan", "vMerge", "tcBorders", "shd", "noWrap", "tcMar", "vAlign"),
                       w=str(widths[ci]), type="dxa")
                el(tcpr, "vAlign", before=("hideMark", "headers"), val="center")
                for p in tc.findall(W + "p"):
                    ppr = p.find(W + "pPr")
                    if ppr is None:
                        ppr = etree.Element(W + "pPr")
                        p.insert(0, ppr)
                    sp = el(ppr, "spacing", before=("ind", "contextualSpacing", "jc", "textAlignment", "rPr"),
                            after="40", line="240", lineRule="auto")
                    sp.set(W + "before", pad)   # "before" is a keyword of el(), so set it here
                    sp.set(W + "after", pad)
                    if not (widths and ci == 1):   # title column stays left-aligned, the rest centred
                        el(ppr, "jc", before=("textDirection", "textAlignment", "rPr"), val="center")
                    if p.find(W + "fldSimple") is not None:   # Word formats a refreshed field like the paragraph mark
                        mrp = el(ppr, "rPr")
                        el(mrp, "rFonts", before=("b", "bCs", "color", "sz", "szCs"), ascii="Times New Roman",
                           hAnsi="Times New Roman", cs="Times New Roman")
                    for fs in p.findall(W + "fldSimple"):   # page numbers in the body font
                        for r in fs.findall(W + "r"):
                            rp = el(r, "rPr", before=("t",))
                            el(rp, "rFonts", before=("b", "sz"), ascii="Times New Roman", hAnsi="Times New Roman",
                               cs="Times New Roman")

    PPR_ORDER = ("pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs "
                 "suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi "
                 "adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection "
                 "textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange").split()
    TBLPR_ORDER = ("tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing "
                   "tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange").split()

    def schema_sort(parent, order):   # el() inserts by a guess; this makes the child order schema-valid
        kids = sorted(parent, key=lambda c: order.index(etree.QName(c).localname)
                      if etree.QName(c).localname in order else len(order))
        for c in kids:
            parent.append(c)

    def sort_table(tbl):
        schema_sort(tbl.find(W + "tblPr"), TBLPR_ORDER)
        for ppr in tbl.iter(W + "pPr"):
            schema_sort(ppr, PPR_ORDER)

    LIST_W = [1300, 5900, 1400]
    for tbl in (t_index, t_figs, t_tabs):
        normalise(tbl, LIST_W)
    normalise(t_contrib, [900, 4900, 2000, 1200], pad="0")   # keeps it and the consolidated table on one page
    normalise(t_cons)
    for tr in t_cons.findall(W + "tr")[:-1]:   # never split the consolidated table across pages
        for ppr in tr.iter(W + "pPr"):
            el(ppr, "keepNext")
    for tbl in (t_index, t_figs, t_tabs, t_contrib, t_cons):
        sort_table(tbl)

    # headings above the lists: one style; drop the template's duplicate black "Index"; List of Tables on a new page
    heads = {"Index": None, "List of Figures": None, "List of Tables": None, "Contributions": None}
    for p in list(body.iter(W + "p")):
        txt = "".join(p.itertext()).strip()
        if txt in heads:
            if txt == "Index" and heads["Index"] is None and p.find(".//" + W + "color") is None:
                nxt = p.getnext()
                p.getparent().remove(p)
                if nxt is not None and not "".join(nxt.itertext()).strip() and nxt.find(".//" + W + "br") is None:
                    nxt.getparent().remove(nxt)
                continue
            heads[txt] = p
            for r in p.findall(W + "r"):
                rp = el(r, "rPr", before=("t", "br", "lastRenderedPageBreak"))
                el(rp, "b", before=("color", "sz", "szCs"))
                el(rp, "color", before=("sz", "szCs"), val="385623")
                el(rp, "sz", before=("szCs",), val="28")
                el(rp, "szCs", val="28")
    # List of Figures, List of Tables and the paper title each start a new page
    for lt in (heads["List of Figures"], heads["List of Tables"], p_title):
        prev = lt.getprevious()
        while prev is not None and prev.tag == W + "p" and not "".join(prev.itertext()).strip() \
                and prev.find(".//" + W + "br") is None and prev.find(".//" + W + "sectPr") is None:
            dead, prev = prev, prev.getprevious()
            dead.getparent().remove(dead)
        el(lt.find(W + "pPr"), "pageBreakBefore")
    for p in (heads["List of Figures"], heads["List of Tables"], p_title, p_auth, p_aff, p_mail, p_mail.getnext(), p_kw):
        schema_sort(p.find(W + "pPr"), PPR_ORDER)

    tree.write(doc_path, xml_declaration=True, encoding="UTF-8", standalone=True)
    rels.write(rels_path, xml_declaration=True, encoding="UTF-8", standalone=True)

    # SmartArt on the cover: register numbers
    for f in ("data1.xml", "drawing1.xml"):
        p = os.path.join(work, "word", "diagrams", f)
        s = open(p, encoding="utf-8").read()
        for reg in REGS:
            s = s.replace("<a:t>Reg No </a:t>", f"<a:t>{reg}</a:t>", 1)
        open(p, "w", encoding="utf-8").write(s)

    # ask Word to refresh PAGEREF fields on open
    sp = os.path.join(work, "word", "settings.xml")
    s = open(sp, encoding="utf-8").read()
    if "<w:updateFields" not in s:
        for anchor in ("<w:hdrShapeDefaults", "<w:footnotePr", "<w:endnotePr", "<w:compat>"):
            if anchor in s:
                s = s.replace(anchor, '<w:updateFields w:val="true"/>' + anchor, 1)
                break
        open(sp, "w", encoding="utf-8").write(s)

    if os.path.exists(a.out):
        os.remove(a.out)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(work):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, work).replace(os.sep, "/"))
    shutil.rmtree(work, ignore_errors=True)

    # -------------------------------------------------- report
    uncited = sorted(set(refs) - set(nums.cite))
    by_type = {"journal": 0, "conference": 0}
    yrs = 0
    for k in nums.cite:
        r = refs[k]
        v = r.get("venue") or ""
        conf = r.get("type") == "conference" or any(w in v for w in ("Proceedings", "Conference", "Symposium", "Workshop",
                                                                      "European Conference")) and "VLDB" not in v
        by_type["conference" if conf else "journal"] += 1
        yrs += 2020 <= int(r["year"]) <= 2025
    total_words = sum(v for v in word_by_sec.values())
    lines = [f"output: {a.out}", f"figures: {len(nums.fig)}  tables: {len(nums.tab)}  equations: {len(nums.eq)}",
             f"references cited: {len(nums.cite)}  (journal {by_type['journal']}, conference/other {by_type['conference']}, "
             f"2020-2025: {yrs})", f"uncited references: {uncited}", f"total words (prose + captions): {total_words}",
             "words per section:"]
    for k, v in word_by_sec.items():
        name = sec_titles.get(k, k) if isinstance(k, int) and k else ("Exec summary + abstract" if k == 0 else k)
        lines.append(f"  {k}: {v}  {name}")
    lines.append("words per member: " + ", ".join(f"{r}={w}" for r, w in totals.items()))
    rep = "\n".join(lines)
    open(os.path.join(HERE, "build_report.txt"), "w", encoding="utf-8").write(rep + "\n")
    print(rep)


if __name__ == "__main__":
    main()
