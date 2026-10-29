"""All manuscript figures as draw.io diagrams (editable .drawio) exported to 600-DPI PNG with draw.io Desktop.

    python paper/drawio_figures.py            # needs draw.io Desktop and paper/results.json

Uniform style: Helvetica 10 px on a fixed canvas width (280 px = one column, 600 px = full width), so every
figure prints at the same text size (~7.5 pt) in the two-column template; one colour palette for all figures;
system colours are identical in every chart. Output:
    paper/Diagrams/drawio/Fig NN <Title>.drawio      (editable in draw.io)
    paper/Diagrams/Fig NN <Title>.png                 (600 DPI, inserted into the manuscript)
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from xml.sax.saxutils import escape

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Diagrams")
SRC = os.path.join(OUT, "drawio")
DRAWIO = os.path.expandvars(r"%LOCALAPPDATA%\Programs\draw.io\draw.io.exe")
SCALE = 600 / 96 * 0.5   # canvas px are rendered at 2x physical size below -> 600 DPI in print
CW, WW = 280, 600        # canvas widths (column / wide)
FONT = "Helvetica"
FS = 11                   # base label size: 11 canvas px = about 8.2 pt in print

BLUE, LBLUE = "#00629B", "#E3F0F8"
GREEN, LGREEN = "#2E7D4F", "#E6F4EC"
ORANGE, LORANGE = "#C77C12", "#FDF1DC"
RED, LRED = "#B03A2E", "#FBE5E3"
PURPLE, LPURPLE = "#6A4C93", "#EFE9F7"
GREY, LGREY = "#555555", "#F2F2F2"
SYS = {"B1_vanilla": "#8C8C8C", "B2_fixed_ckpt": "#5B8DB8", "B3_naive_ha": "#E3A23B", "P_rmc": "#2E8B57"}
SYS_SHORT = {"B1_vanilla": "B1 Vanilla", "B2_fixed_ckpt": "B2 Fixed ckpt", "B3_naive_ha": "B3 Naive HA", "P_rmc": "P RMC-Spark"}
ORDER = ["B1_vanilla", "B2_fixed_ckpt", "B3_naive_ha", "P_rmc"]


_FONTS = {}


def _lines(text, width, fs, bold):
    """Wrapped line count of a label, measured with Arial (metric-compatible with Helvetica)."""
    from PIL import ImageFont
    key = (round(fs * 4), bold)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size=fs * 4)   # 4x for precision
    font = _FONTS[key]
    n = 0
    if any(font.getlength(wd) / 4 > width for wd in str(text).split()):
        return 99          # a single word wider than the label cannot wrap: never acceptable
    for para in str(text).split("\n"):
        line = ""
        n += 1
        for word in para.split(" "):
            cand = f"{line} {word}".strip()
            if line and font.getlength(cand) / 4 > width:
                n += 1
                line = word
            else:
                line = cand
    return n


def fit_fs(text, w, h, fs, bold=False, box=True):
    """Largest size from fs down to fs - 1 (the original design size) that keeps the label's line
    count of the original design and, for boxes, fits the box height; never smaller than the original."""
    if not text:
        return fs
    pad = 4                    # draw.io wraps html labels at width - 2 x spacing (spacing=2)
    # original wrapping measured with draw.io's real padding; a larger size must fit with an extra safety margin
    base = _lines(text, max(w - pad, 1), fs - 1, bold)
    for cand in (fs, fs - 0.5):
        n = _lines(text, max(w - pad - 6, 1), cand, bold)
        if n <= base and n < 99 and (not box or n * cand * 1.3 <= h - 2):
            return cand
    return fs - 1


class Fig:
    def __init__(self, width):
        self.w = width
        self.cells = []
        self.n = 1
        self.maxy = 0

    @staticmethod
    def _h(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _id(self):
        self.n += 1
        return f"c{self.n}"

    def _track(self, y, h):
        self.maxy = max(self.maxy, y + h)

    def box(self, x, y, w, h, text="", fill=LBLUE, stroke=BLUE, fs=FS, bold=False, color="#1A1A1A", rounded=1,
            dashed=False, align="center", valign="middle", shape="", extra=""):
        i = self._id()
        if not shape:
            fs = fit_fs(text, w, h, fs, bold)
        st = (f"{shape}rounded={rounded};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontFamily={FONT};"
              f"fontSize={fs};fontColor={color};align={align};verticalAlign={valign};arcSize=12;spacing=2;"
              f"{'fontStyle=1;' if bold else ''}{'dashed=1;' if dashed else ''}{extra}")
        self.cells.append(f'<mxCell id="{i}" value="{escape(self._h(text), {chr(34): "&quot;"})}" style="{st}" vertex="1" parent="1">'
                          f'<mxGeometry x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" as="geometry"/></mxCell>')
        self._track(y, h)
        return i

    def group(self, x, y, w, h, title, fill=LGREY, stroke=GREY, fs=FS, color=None, dashed=False):
        return self.box(x, y, w, h, title, fill=fill, stroke=stroke, fs=fs, bold=True, color=color or stroke,
                        align="left", valign="top", dashed=dashed, extra="spacingLeft=4;spacingTop=1;")

    def text(self, x, y, w, h, text, fs=FS, color="#1A1A1A", bold=False, align="center", italic=False, rotation=0):
        i = self._id()
        if not rotation:
            fs = fit_fs(text, w, h, fs, bold, box=False)
        style = (f"text;html=1;whiteSpace=wrap;fontFamily={FONT};fontSize={fs};fontColor={color};align={align};"
                 f"verticalAlign=middle;{'fontStyle=' + str((1 if bold else 0) + (2 if italic else 0)) + ';' if bold or italic else ''}"
                 f"{'rotation=' + str(rotation) + ';' if rotation else ''}")
        self.cells.append(f'<mxCell id="{i}" value="{escape(self._h(text), {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
                          f'<mxGeometry x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" as="geometry"/></mxCell>')
        self._track(y, h)
        return i

    def edge(self, s, t, label="", color=GREY, dashed=False, both=False, ortho=True, width=1, fs=FS - 2, extra=""):
        i = self._id()
        st = (f"{'edgeStyle=orthogonalEdgeStyle;' if ortho else ''}rounded=0;html=1;strokeColor={color};strokeWidth={width};"
              f"fontFamily={FONT};fontSize={fs};fontColor={color};endArrow=block;endSize=4;"
              f"{'startArrow=block;startSize=4;' if both else ''}{'dashed=1;' if dashed else ''}labelBackgroundColor=#FFFFFF;{extra}")
        self.cells.append(f'<mxCell id="{i}" value="{escape(label, {chr(34): "&quot;"})}" style="{st}" edge="1" parent="1" '
                          f'source="{s}" target="{t}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        return i

    def line(self, pts, color=GREY, width=1, dashed=False, arrow=False, label=""):
        i = self._id()
        (x0, y0), (x1, y1), mid = pts[0], pts[-1], pts[1:-1]
        arr = "".join(f'<mxPoint x="{x:.1f}" y="{y:.1f}"/>' for x, y in mid)
        st = (f"html=1;rounded=0;strokeColor={color};strokeWidth={width};endArrow={'block;endSize=4' if arrow else 'none'};"
              f"{'dashed=1;' if dashed else ''}fontFamily={FONT};fontSize={FS - 2};fontColor={color};")
        self.cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{st}" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                          f'<mxPoint x="{x0:.1f}" y="{y0:.1f}" as="sourcePoint"/><mxPoint x="{x1:.1f}" y="{y1:.1f}" as="targetPoint"/>'
                          f'{"<Array as=" + chr(34) + "points" + chr(34) + ">" + arr + "</Array>" if mid else ""}</mxGeometry></mxCell>')
        for _, y in pts:
            self._track(y, 0)
        return i

    def xml(self, name):
        frame = (f'<mxCell id="frame" value="" style="rounded=0;fillColor=none;strokeColor=none;" vertex="1" parent="1">'
                 f'<mxGeometry x="0" y="0" width="{self.w}" height="{self.maxy + 2:.0f}" as="geometry"/></mxCell>')
        return (f'<mxfile host="drawio"><diagram name="{escape(name)}"><mxGraphModel dx="0" dy="0" grid="0" page="0">'
                f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{frame}{"".join(self.cells)}</root></mxGraphModel></diagram></mxfile>')


def export(fig, name):
    os.makedirs(SRC, exist_ok=True)
    src = os.path.join(SRC, f"{name}.drawio")
    png = os.path.join(OUT, f"{name}.png")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(fig.xml(name))
    # canvas px -> 600 DPI at the printed width: column = 2.89 in, wide = 6.27 in
    inches = 2.89 if fig.w == CW else 6.27
    scale = round(600 * inches / fig.w, 3)
    subprocess.run([DRAWIO, "--export", "--format", "png", "--scale", str(scale), "--border", "0", "--output", png, src],
                   check=True, capture_output=True)
    im = Image.open(png).convert("RGB")
    im.save(png, dpi=(600, 600))
    return png


# ============================================================================ chart helpers
def axes(f, x0, y0, w, h, ymax, yticks, ylabel, xlabels=None, xlabel=""):
    """Plot area with origin at (x0, y0 + h). Returns a y-mapper."""
    f.line([(x0, y0), (x0, y0 + h), (x0 + w, y0 + h)], color="#333333")
    for v in yticks:
        y = y0 + h - h * v / ymax
        f.line([(x0, y), (x0 + w, y)], color="#DDDDDD")
        f.text(x0 - 34, y - 6, 31, 12, f"{v:g}", fs=FS - 1, align="right")
    f.text(x0 - 46, y0 + h / 2 - 50, 14, 100, ylabel, fs=FS - 1, rotation=-90)
    if xlabel:
        f.text(x0, y0 + h + 22, w, 12, xlabel, fs=FS - 1)
    return lambda v: y0 + h - h * min(v, ymax) / ymax


def legend(f, x, y, items, per_row=4, step=None):
    step = step or 140
    for k, (lab, col) in enumerate(items):
        cx, cy = x + (k % per_row) * step, y + (k // per_row) * 14
        f.box(cx, cy + 2, 9, 9, fill=col, stroke=col, rounded=0)
        f.text(cx + 12, cy, step - 14, 13, lab, fs=FS - 1, align="left")


# ============================================================================ figures
def fig01():
    f = Fig(CW)
    f.text(0, 0, CW, 14, "Scope of fault tolerance widens with each generation", bold=True, color=BLUE)
    f.line([(6, 92), (274, 92)], color=BLUE, width=2, arrow=True)
    items = [(30, "2004", "MapReduce", "task re-execution"), (74, "2012-13", "RDDs, YARN", "lineage recomputation"),
             (118, "2015", "Flink, Spark SQL", "distributed snapshots"), (162, "2015-16", "Borg, Kubernetes", "orchestrated restarts"),
             (206, "2018", "Structured Streaming", "exactly-once checkpoints"), (250, "2020+", "multi-cluster cloud", "cross-cluster resilience")]
    for k, (x, yr, name, ft) in enumerate(items):
        up = k % 2 == 0
        f.box(x - 3, 89, 6, 6, fill=BLUE, stroke=BLUE, rounded=1, extra="arcSize=50;")
        f.text(x - 22, 96 if up else 74, 44, 12, yr, fs=FS - 1, color=GREY)
        last = k == len(items) - 1
        f.box(x - 25, 30 if up else 112, 50, 40, name, fill=LGREEN if last else LBLUE, stroke=GREEN if last else BLUE, fs=FS - 1, bold=True)
        f.text(x - 43, 16 if up else 153, 86, 13, ft, fs=FS - 2, color=GREY, italic=True)
    return f


def fig02():
    f = Fig(CW)
    teams = [("Data engineers", 0), ("Data scientists", 70), ("Platform engineers", 140)]
    ids = [f.box(x, 0, 66, 26, t, fill=LORANGE, stroke=ORANGE, bold=True) for t, x in teams]
    layers = [("Analytics programs: pipelines, features, models (rds stages)", LGREEN, GREEN),
              ("Platform services: Spark clusters, controller, monitoring", LBLUE, BLUE),
              ("Shared storage: object store, data lake, checkpoints", LPURPLE, PURPLE)]
    lid = []
    for k, (t, fc, ec) in enumerate(layers):
        lid.append(f.box(0, 44 + k * 40, 206, 32, t, fill=fc, stroke=ec))
    for i in ids:
        f.edge(i, lid[0], color=ORANGE, ortho=False)
    f.group(214, 0, 66, 156, "Failure sources", fill=LRED, stroke=RED)
    for k, t in enumerate(["code bugs", "executor OOM", "node loss", "network", "storage", "cluster outage"]):
        f.text(216, 30 + k * 20, 62, 14, t, fs=FS - 1, color=RED)
    f.text(0, 162, CW, 14, "Resilience must span programs, platform and storage", bold=True, color=BLUE)
    return f


def fig03():
    f = Fig(CW)
    for x, t in ((2, "Scope"), (50, "Example"), (170, "First responder")):
        f.text(x, 0, 110, 13, t, fs=FS - 1, bold=True, color=GREY, align="left")
    rows = [("Task", "executor crash, OOM, bad record", "Spark task retry", LGREEN, GREEN, 150),
            ("Node", "worker host or disk lost", "Spark reschedules, recomputes", LBLUE, BLUE, 190),
            ("Gray", "network delay, straggler, slow disk", "often nobody (speculation)", LORANGE, ORANGE, 230),
            ("Cluster", "master loss, partition, zone outage", "nobody in B1; RMC-Spark controller", LRED, RED, 266)]
    for k, (n, ex, r, fc, ec, w) in enumerate(rows):
        y = 16 + k * 38
        f.box(0, y, CW, 32, "", fill=fc, stroke=ec)
        f.text(3, y, 46, 32, n, bold=True, color=ec, align="left")
        f.text(48, y, 118, 32, ex, fs=FS - 1, align="left")
        f.text(168, y, 100, 32, r, fs=FS - 1, color=ec, align="left")
    f.text(0, 170, CW, 13, "blast radius grows from top to bottom", fs=FS - 1, italic=True, color=GREY)
    return f


def fig04():
    f = Fig(WW)
    root = f.box(220, 0, 160, 26, "Resilient distributed analytics", fill=BLUE, stroke=BLUE, color="#FFFFFF", bold=True)
    br = [("Engine-level recovery", ["RDD lineage", "recomputation (RCMP)", "lineage checkpoint", "write-ahead lineage"]),
          ("Checkpoint optimisation", ["Young / Daly interval", "online MTBF (En-CHORE)", "stream-optimal interval", "failure-aware (FATM)"]),
          ("Stragglers and gray failures", ["LATE, Mantri", "RL identification", "tuple scheduling", "gray-failure model"]),
          ("Prediction and AIOps", ["task / node failure", "disk failure", "anomaly detection", "root-cause analysis"]),
          ("Multi-cluster orchestration", ["Borg / Kubernetes", "multi-cloud scheduling", "geo-distributed analytics", "RL multi-cloud Spark"]),
          ("Resilience engineering", ["chaos engineering", "reliability models", "recovery benchmarks", "SLO / SLA"])]
    bw = 96
    for k, (t, leaves) in enumerate(br):
        x = k * (bw + 4.8)
        b = f.box(x, 48, bw, 32, t, bold=True)
        f.edge(root, b, color=BLUE, ortho=False)
        for j, leaf in enumerate(leaves):
            f.box(x + 4, 90 + j * 26, bw - 8, 22, leaf, fill="#FFFFFF", stroke=GREY, fs=FS - 1)
    f.box(150, 200, 300, 22, "RMC-Spark combines elements of all six branches", fill=LGREEN, stroke=GREEN, bold=True)
    return f


def fig05():
    f = Fig(CW)
    cols = [("Stakeholders", ["data scientists", "data engineers", "platform team", "business owner"], LORANGE, ORANGE),
            ("Requirements", ["F1-F7 functional", "N1 availability", "N2 overhead", "N3-N5 quality"], LBLUE, BLUE),
            ("Components", ["C1 monitor", "C2 checkpoints", "C3 failover", "C4, C5"], LGREEN, GREEN),
            ("Verification", ["56 unit tests", "simulation", "fault runs", "design review"], LPURPLE, PURPLE)]
    prev = None
    for k, (t, items, fc, ec) in enumerate(cols):
        x = k * 71
        f.text(x, 0, 66, 13, t, fs=FS - 1, bold=True, color=ec)
        ids = [f.box(x, 16 + j * 32, 66, 26, it, fill=fc, stroke=ec, fs=FS - 1) for j, it in enumerate(items)]
        if prev:
            f.edge(prev[1], ids[1], color=GREY)
        prev = ids
    f.text(0, 146, CW, 13, "traceability: concern → requirement → component → evidence", fs=FS - 1, italic=True, color=GREY)
    return f


def fig06():
    f = Fig(WW)
    f.group(0, 0, 170, 168, "Controller container", fill=LGREEN, stroke=GREEN)
    api = f.box(8, 20, 154, 26, "REST API · Prometheus exporter · CLI", fill="#FFFFFF", stroke=GREEN)
    loop = f.box(8, 56, 154, 48, "Control loop (2 s): C1 health · C3 failover · C4 placement · C5 decision log · MTBF", fill="#FFFFFF", stroke=GREEN)
    drv = f.box(8, 120, 154, 40, "Spark drivers (client mode), attempt n + rds library (C2)", fill="#FFFFFF", stroke=GREEN)
    f.edge(loop, drv, "start / stop", color=GREEN)
    clusters = []
    for k, n in enumerate("AB"):
        x = 200 + k * 205
        f.group(x, 0, 190, 168, f"Spark cluster {n}", fill=LBLUE, stroke=BLUE)
        m = f.box(x + 50, 22, 90, 26, f"master {n}", fill="#FFFFFF", stroke=BLUE, bold=True)
        w1 = f.box(x + 10, 92, 80, 44, f"worker {n.lower()}1, 2 executors", fill="#FFFFFF", stroke=BLUE)
        w2 = f.box(x + 100, 92, 80, 44, f"worker {n.lower()}2, 2 executors", fill="#FFFFFF", stroke=BLUE)
        f.edge(m, w1, color=BLUE)
        f.edge(m, w2, color=BLUE)
        clusters.append((m, w1, w2))
    store = f.box(200, 196, 395, 34, "Shared object storage (MinIO / S3): data · checkpoints + commit markers · results",
                  fill=LPURPLE, stroke=PURPLE, bold=True)
    for m, w1, w2 in clusters:
        f.edge(w1, store, color=PURPLE, both=True)
        f.edge(w2, store, color=PURPLE, both=True)
    f.edge(api, clusters[0][0], "probe /json", color=GREEN)
    f.edge(drv, clusters[0][1], "executors", color=BLUE, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    f.edge(drv, clusters[1][2], "failover: next attempt on B", color=BLUE, dashed=True,
           extra="exitX=1;exitY=0.85;entryX=0.5;entryY=1;")
    prom = f.box(0, 196, 80, 34, "Prometheus (scrapes all)", fill=LORANGE, stroke=ORANGE, bold=True, fs=FS - 1)
    graf = f.box(90, 196, 80, 34, "Grafana", fill=LORANGE, stroke=ORANGE, bold=True)
    f.edge(prom, graf, color=ORANGE)
    f.box(200, 244, 395, 24, "Fault injector (Docker API): kill · pause · tc netem · network disconnect", fill=LRED, stroke=RED, fs=FS - 1)
    return f


def fig07():
    f = Fig(CW)
    layers = [("Governance: access, audit, policies (XII)", LGREY, GREY), ("Explainability: decision log, score R (XI)", LPURPLE, PURPLE),
              ("Control: monitor, detect, recover, place (VIII-X)", LGREEN, GREEN), ("Resilience programming: rds stages (IX)", LORANGE, ORANGE),
              ("Processing: Spark clusters A and B (VII)", LBLUE, BLUE), ("Storage: shared object store (VI)", LPURPLE, PURPLE)]
    for k, (t, fc, ec) in enumerate(layers):
        f.box(0, k * 30, 220, 26, t, fill=fc, stroke=ec)
    f.box(228, 0, 52, 176, "Observability (Prometheus, Grafana, events)", fill="#FFFFFF", stroke=ORANGE, fs=FS - 1)
    return f


def fig08():
    f = Fig(WW)
    srcs = [f.box(0, k * 30, 100, 24, t, fill=LORANGE, stroke=ORANGE, fs=FS - 1) for k, t in
            enumerate(["Synthetic generator (seeded)", "NYC TLC trips", "AI4I 2020", "ULB credit card"])]
    data = f.box(124, 30, 60, 54, "data bucket", fill=LPURPLE, stroke=PURPLE, bold=True)
    for s in srcs:
        f.edge(s, data, color=ORANGE, ortho=False)
    prev = data
    st = []
    for k, n in enumerate(["clean", "enrich", "hourly_agg", "zone_rank"]):
        b = f.box(208 + k * 84, 34, 70, 46, f"stage {n}", fill=LGREEN, stroke=GREEN, bold=True)
        f.edge(prev, b, color=GREEN)
        prev = b
        st.append(b)
    res = f.box(548, 30, 52, 54, "results bucket", fill=LPURPLE, stroke=PURPLE, bold=True)
    f.edge(prev, res, color=GREEN)
    ck = f.box(208, 118, 322, 26, "checkpoint bucket: <job>/<stage>/data, then _RDS_COMMIT marker (written last)", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    for b in st:
        f.edge(b, ck, color=PURPLE, dashed=True)
    f.text(208, 0, 322, 26, "restore if committed, else compute, materialise and let the policy decide", fs=FS - 1, italic=True, color=GREEN)
    return f


def fig09():
    f = Fig(CW)
    f.group(0, 0, 112, 104, "Controller container", fill=LGREEN, stroke=GREEN)
    d = f.box(6, 20, 100, 76, "Driver: SparkSession, Catalyst, DAG scheduler, task scheduler", fill="#FFFFFF", stroke=GREEN)
    f.group(126, 0, 154, 104, "Cluster (standalone)", fill=LBLUE, stroke=BLUE)
    m = f.box(140, 20, 126, 22, "master: allocation", fill="#FFFFFF", stroke=BLUE)
    w1 = f.box(132, 54, 68, 42, "worker: executors, tasks, cache", fill="#FFFFFF", stroke=BLUE, fs=FS - 1)
    w2 = f.box(206, 54, 68, 42, "worker: executors, tasks, cache", fill="#FFFFFF", stroke=BLUE, fs=FS - 1)
    f.edge(d, m, "register", color=GREY)
    f.edge(d, w1, "tasks", color=GREY, both=True)
    s = f.box(0, 124, CW, 24, "Shared object storage (S3A)", fill=LPURPLE, stroke=PURPLE, bold=True)
    for b in (w1, w2):
        f.edge(b, s, color=PURPLE, both=True)
    f.edge(d, s, color=PURPLE, dashed=True, both=True)
    return f


def fig10(R):
    f = Fig(WW)
    m = R["stage_median_s"]
    rs = [("clean", ["read parquet", "filter / withColumn"], BLUE, f"narrow, median {m['clean']} s"),
          ("enrich", ["broadcast join x2"], BLUE, f"narrow, median {m['enrich']} s"),
          ("hourly_agg", ["groupBy (shuffle)", "agg, percentile"], ORANGE, f"wide, median {m['hourly_agg']} s"),
          ("zone_rank", ["groupBy (shuffle)", "window rank"], ORANGE, f"wide, median {m['zone_rank']} s")]
    prev = None
    for k, (n, ops, c, note) in enumerate(rs):
        x = k * 152
        g = f.group(x, 0, 136, 118, f"resilient stage: {n}", fill=LGREEN, stroke=GREEN)
        for j, op in enumerate(ops):
            f.box(x + 10, 22 + j * 34, 116, 26, op, fill="#FFFFFF", stroke=c)
        f.text(x, 98, 136, 14, note, fs=FS - 1, italic=True, color=GREY)
        if prev:
            f.edge(prev, g, color=GREEN)
            f.line([(x - 8, 0), (x - 8, 132)], color=RED, dashed=True)
        prev = g
    f.text(0, 134, WW, 14, "dashed red: commit marker = lineage cut (if the policy checkpoints); stage times from the clean B1 runs",
           fs=FS - 1, color=RED)
    return f


def fig11():
    f = Fig(CW)
    sp = f.box(0, 0, 76, 40, "Spark masters, workers (probe every 2 s)", fs=FS - 1)
    dr = f.box(0, 60, 76, 40, "Spark drivers (task progress)", fs=FS - 1)
    ctl = f.box(98, 0, 86, 100, "Controller: probes, signals, health H, state machine, decisions", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    pr = f.box(206, 0, 74, 40, "Prometheus (5 s scrape)", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    gr = f.box(206, 60, 74, 40, "Grafana dashboard", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    f.edge(sp, ctl, color=GREEN)
    f.edge(dr, ctl, color=GREEN)
    f.edge(ctl, pr, color=ORANGE)
    f.edge(pr, gr, color=ORANGE)
    f.box(0, 114, CW, 22, "decision path (direct, 2 s) vs operator path (Prometheus / Grafana, 5 s)", fill="#FFFFFF", stroke=GREY, fs=FS - 1)
    return f


def fig12():
    f = Fig(CW)
    steps = ["poll every 2 s", "probe master + driver", "5 signals → a_i", "H = 1 − Σ w_i a_i", "update state machine"]
    prev = None
    for k, s in enumerate(steps):
        b = f.box(0, k * 30, 104, 22, s, fs=FS - 1)
        if prev:
            f.edge(prev, b, color=BLUE)
        prev = b
    h = f.box(190, 0, 80, 24, "HEALTHY", fill=LGREEN, stroke=GREEN, bold=True)
    s = f.box(190, 60, 80, 24, "SUSPECT", fill=LORANGE, stroke=ORANGE, bold=True)
    fa = f.box(190, 120, 80, 24, "FAILED", fill=LRED, stroke=RED, bold=True)
    f.edge(h, s, "H < 0.95", color=ORANGE)
    f.edge(s, fa, "3 polls H < 0.50", color=RED)
    f.edge(fa, h, "", color=GREEN, extra="exitX=0;exitY=0.5;entryX=0;entryY=0.5;")
    f.text(110, 64, 66, 26, "5 polls H ≥ 0.95", fs=FS - 1, color=GREEN, align="right")
    return f


def daly(c, m):
    if c >= 2 * m:
        return m
    r = c / (2 * m)
    return math.sqrt(2 * c * m) * (1 + math.sqrt(r) / 3 + r / 9) - c


def fig13():
    f = Fig(CW)
    f.text(0, 0, 30, 14, "(a)", bold=True, align="left")
    lv = [("Task level", "Spark retries tasks, recomputes lost partitions", LGREEN, GREEN),
          ("Attempt level", "crash on healthy cluster → retry there, restore stages", LBLUE, BLUE),
          ("Cluster level", "cluster FAILED and job stalled → new attempt on argmin J", LRED, RED)]
    for k, (n, t, fc, ec) in enumerate(lv):
        y = 18 + k * 32
        f.box(0, y, 70, 26, n, fill=fc, stroke=ec, bold=True, fs=FS - 1)
        f.box(76, y, 204, 26, t, fill="#FFFFFF", stroke=ec, fs=FS - 1, align="left")
    f.text(0, 122, 30, 14, "(b)", bold=True, align="left")
    x0, y0, w, h = 48, 140, 222, 120
    lx = lambda m: x0 + w * (math.log10(m) - math.log10(60)) / (math.log10(7200) - math.log10(60))
    ly = lambda v: y0 + h - h * (math.log10(v) - math.log10(5)) / (math.log10(500) - math.log10(5))
    f.line([(x0, y0), (x0, y0 + h), (x0 + w, y0 + h)], color="#333333")
    for v in (5, 10, 50, 100, 500):
        f.line([(x0, ly(v)), (x0 + w, ly(v))], color="#DDDDDD")
        f.text(x0 - 30, ly(v) - 6, 27, 12, str(v), fs=FS - 1, align="right")
    for m in (60, 300, 900, 3600, 7200):
        f.text(lx(m) - 16, y0 + h + 2, 32, 12, str(m), fs=FS - 1)
    f.text(x0, y0 + h + 14, w, 12, "MTBF M (s), log scale", fs=FS - 1)
    f.text(x0 - 46, y0 + 10, 14, 100, "seconds (log)", fs=FS - 1, rotation=-90)
    ms = [60 * (7200 / 60) ** (k / 40) for k in range(41)]
    for c, col in ((2, GREEN), (5, BLUE), (10, RED)):
        f.line([(lx(m), ly(daly(c, m))) for m in ms], color=col, width=1.5)
        f.line([(lx(m), ly(daly(c, m) / 2 + c)) for m in ms], color=col, width=1, dashed=True)
    legend(f, x0, y0 + h + 28, [("C = 2 s", GREEN), ("C = 5 s", BLUE), ("C = 10 s", RED)], per_row=3, step=70)
    f.text(x0, y0 + h + 42, w, 12, "solid: τ* (Eq. 4)   dashed: expected lost work (Eq. 5)", fs=FS - 1, color=GREY)
    return f


def fig14(R):
    p = R["cells"]["P_rmc|cluster_outage"]
    f = Fig(CW)
    steps = [("t0", "fault: cluster A outage", LRED, RED),
             ("+0 s", "first probe fails: H = 0.30 → SUSPECT", LORANGE, ORANGE),
             (f"+{p['median_detect_s']} s", "3 polls H < 0.50 → A FAILED (logged)", LORANGE, ORANGE),
             ("", "job still progressing → keep (logged)", LORANGE, ORANGE),
             (f"+{p['median_action_s']} s", "no progress 10 s → kill driver, argmin J → B", LGREEN, GREEN),
             ("", "spark-submit attempt n+1 on master B", LGREEN, GREEN),
             ("", "rds: restore committed stages, compute rest", LBLUE, BLUE),
             ("end", "job SUCCEEDED, reliability updated", LBLUE, BLUE)]
    prev = None
    for k, (t, s, fc, ec) in enumerate(steps):
        y = k * 28
        b = f.box(54, y, 226, 22, s, fill=fc, stroke=ec, fs=FS - 1)
        f.text(0, y, 50, 22, t, fs=FS - 1, color=GREY, align="right")
        if prev:
            f.edge(prev, b, color=GREY)
        prev = b
    f.text(0, 226, CW, 12, "times: medians of the measured RMC-Spark outage runs", fs=FS - 1, italic=True, color=GREY)
    return f


def fig15():
    f = Fig(CW)
    c = f.box(80, 0, 120, 36, "Controller (cluster view, job attempts)", fill=LGREEN, stroke=GREEN, bold=True)
    a = f.box(0, 70, 90, 34, "Cluster A", bold=True)
    b = f.box(190, 70, 90, 34, "Cluster B", bold=True)
    s = f.box(60, 140, 160, 34, "Object storage: job state + commit markers", fill=LPURPLE, stroke=PURPLE)
    f.edge(c, a, "probe · attempt", color=GREEN)
    f.edge(c, b, "probe · attempt", color=GREEN)
    f.edge(a, s, color=PURPLE, both=True)
    f.edge(b, s, color=PURPLE, both=True)
    f.text(92, 80, 96, 14, "no direct coordination", fs=FS - 1, color=RED)
    return f


def fig16():
    f = Fig(CW)
    t = f.box(0, 0, 84, 34, "trigger: submit, retry, failover", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    e = f.box(98, 0, 84, 34, "eligibility: drop FAILED / excluded", fs=FS - 1)
    s = f.box(196, 0, 84, 34, "score J = αL + β(1−H) + γT", fs=FS - 1)
    a = f.box(196, 52, 84, 34, "argmin J, tie → name order", fs=FS - 1)
    l = f.box(98, 52, 84, 34, "decision log: all J_k + reason", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    sb = f.box(0, 52, 84, 34, "spark-submit to chosen master", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    for x, y in ((t, e), (e, s), (s, a), (a, l), (l, sb)):
        f.edge(x, y)
    f.box(0, 100, CW, 30, "α = 0.4 (load), β = 0.5 (health), γ = 0.1 (transfer; 0 in testbed). No eligible cluster → job waits",
          fill="#FFFFFF", stroke=GREY, fs=FS - 1)
    return f


def fig17():
    f = Fig(CW)
    sig = [f.box(0, k * 24, 80, 20, f"a: {s}", fs=FS - 1) for k, s in enumerate(["unreachable", "workers_lost", "latency", "stall", "executor_loss"])]
    c = f.box(100, 34, 70, 48, "contributions w_i·a_i (sum → H)", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    for s in sig:
        f.edge(s, c, color=GREY, ortho=False)
    t = f.box(190, 10, 90, 34, "transition record: state, H, top causes", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    fo = f.box(190, 70, 90, 34, "failover record: source, target, all J_k", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    r = f.box(100, 130, 100, 34, "reliability score R: availability, recovery, success, health", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    o = f.box(214, 130, 66, 34, "API, Grafana, audit", fill="#FFFFFF", stroke=GREY, fs=FS - 1)
    f.edge(c, t)
    f.edge(c, fo)
    f.edge(c, r)
    f.edge(r, o)
    return f


def fig18():
    f = Fig(CW)
    f.text(0, 0, CW, 12, "solid: implemented   dashed: designed, not enabled", fs=FS - 1, color=GREY)
    u = f.box(0, 24, 62, 30, "users (roles)", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    idp = f.box(0, 72, 62, 30, "identity provider", fill="#FFFFFF", stroke=ORANGE, fs=FS - 1, dashed=True)
    f.group(74, 16, 206, 140, "Private container network")
    f.box(80, 36, 92, 26, "Spark clusters", fs=FS - 1)
    f.box(182, 36, 92, 26, "Object storage", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    api = f.box(80, 72, 92, 34, "Controller API + decision log (audit)", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    f.box(182, 72, 92, 34, "credentials / secret store", fill="#FFFFFF", stroke=GREY, dashed=True, fs=FS - 1)
    f.box(80, 118, 194, 30, "TLS · Spark auth · bucket policies · non-root", fill="#FFFFFF", stroke=RED, dashed=True, fs=FS - 1)
    f.edge(u, api, "RBAC", color=ORANGE, dashed=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    return f


def fig19():
    f = Fig(WW)
    f.group(0, 0, WW, 158, "Host: 12 logical CPUs, 16 GB RAM, Windows 11, Docker 28.3 (WSL2, 12 GB)")
    for k, n in enumerate("AB"):
        x = 8 + k * 136
        f.group(x, 20, 128, 92, f"cluster {n}", fill=LBLUE, stroke=BLUE)
        f.box(x + 8, 40, 112, 20, f"master {n} (768 MB)", fill="#FFFFFF", stroke=BLUE, fs=FS - 1)
        f.box(x + 6, 68, 56, 36, "worker 2 c / 1.75 GB", fill="#FFFFFF", stroke=BLUE, fs=FS - 1)
        f.box(x + 66, 68, 56, 36, "worker 2 c / 1.75 GB", fill="#FFFFFF", stroke=BLUE, fs=FS - 1)
    f.group(284, 20, 170, 92, "controller (2.5 GB)", fill=LGREEN, stroke=GREEN)
    for k, t in enumerate(["drivers + rds", "experiment runner", "fault injector"]):
        f.box(292, 40 + k * 24, 154, 20, t, fill="#FFFFFF", stroke=RED if k == 2 else GREEN, fs=FS - 1)
    for k, t in enumerate(["MinIO (512 MB)", "Prometheus", "Grafana"]):
        f.box(462, 20 + k * 32, 130, 26, t, fill=LPURPLE if k == 0 else LORANGE, stroke=PURPLE if k == 0 else ORANGE, fs=FS - 1)
    f.box(8, 124, 446, 26, "Docker Engine API ← fault injector: kill · pause · tc netem · network disconnect · cpu quota",
          fill="#FFFFFF", stroke=RED, dashed=True, fs=FS - 1)
    f.box(462, 124, 130, 26, "bridge network rmc-net", fill="#FFFFFF", stroke=GREY, fs=FS - 1)
    return f


def fig20():
    f = Fig(WW)
    raw = ["runs.csv", "decisions.jsonl", "events/*.jsonl", "cluster_timeseries.csv"]
    met = ["job: success, duration, delay, downtime", "recovery: detection, failover", "work: recomputed, checkpoint cost", "resource: utilisation U"]
    st = f.box(380, 30, 110, 70, "statistics: medians, Fisher exact test, Mann-Whitney U (where n allows)", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    for k, (r, m) in enumerate(zip(raw, met)):
        a = f.box(0, k * 34, 120, 26, r, fill=LORANGE, stroke=ORANGE)
        b = f.box(160, k * 34, 180, 26, m, fs=FS - 1)
        f.edge(a, b)
        f.edge(b, st, ortho=False)
    o = f.box(512, 30, 88, 70, "Tables 11-13, 15; Figs 21-24, 28", fill=LPURPLE, stroke=PURPLE, bold=True)
    f.edge(st, o)
    return f


def fig21(R):
    f = Fig(WW)
    C = R["cells"]
    f.text(0, 0, 290, 14, "(a) Median completion time per scenario", bold=True, align="left")
    x0, y0, w, h = 50, 22, 236, 150
    ym = axes(f, x0, y0, w, h, 800, [0, 200, 400, 600, 800], "completion time (s)")
    groups = [("none", "no fault"), ("executor_kill", "executor kill"), ("cluster_outage", "cluster outage")]
    gw, bw = w / 3, 13
    for gi, (fault, lab) in enumerate(groups):
        gx = x0 + gi * gw + 9
        for si, s in enumerate(ORDER):
            c = C.get(f"{s}|{fault}")
            if not c:
                continue
            v = c["median_duration_s"]
            x = gx + si * (bw + 3)
            failed = c["succeeded"] < c["n"]
            f.box(x, ym(v), bw, y0 + h - ym(v), "", fill=SYS[s], stroke=RED if failed else SYS[s], rounded=0,
                  extra="fillStyle=hatch;" if failed else "")
            f.text(x - 6, ym(v) - 13, bw + 12, 12, f"{v:.0f}", fs=FS - 2)
            f.text(x - 4, y0 + h + 1, bw + 8, 11, f"n={c['n']}", fs=FS - 3, color=GREY)
        f.text(x0 + gi * gw, y0 + h + 11, gw, 12, lab, fs=FS - 1)
    f.text(50, y0 + h + 46, 540, 12, "hatched bars: every run failed at the 716 s deadline (value shown = time at deadline)", fs=FS - 2, color=RED)
    f.text(310, 0, 290, 14, "(b) Cluster outage: time from fault to action", bold=True, align="left")
    x1, w1 = 360, 228
    ym2 = axes(f, x1, y0, w1, h, 35, [0, 10, 20, 30], "seconds after fault")
    bars = [("B1_vanilla", "detect", C["B1_vanilla|cluster_outage"]["median_detect_s"], "no action"),
            ("B2_fixed_ckpt", "detect", C["B2_fixed_ckpt|cluster_outage"]["median_detect_s"], "no action"),
            ("B3_naive_ha", "detect = failover", C["B3_naive_ha|cluster_outage"]["median_action_s"], ""),
            ("P_rmc", "detect", C["P_rmc|cluster_outage"]["median_detect_s"], ""),
            ("P_rmc", "failover", C["P_rmc|cluster_outage"]["median_action_s"], "")]
    for k, (s, kind, v, note) in enumerate(bars):
        x = x1 + 12 + k * 44
        f.box(x, ym2(v), 26, y0 + h - ym2(v), "", fill=SYS[s], stroke=SYS[s], rounded=0,
              extra="opacity=55;" if kind == "detect" and s == "P_rmc" else "")
        f.text(x - 6, ym2(v) - 13, 38, 12, f"{v:.1f}", fs=FS - 2)
        f.text(x - 9, y0 + h + 1, 44, 22, f"{SYS_SHORT[s].split()[0]} {kind}" + (f" ({note})" if note else ""), fs=FS - 3)
    legend(f, 50, y0 + h + 30, [(SYS_SHORT[s], SYS[s]) for s in ORDER], per_row=4, step=130)
    return f


def fig22(R):
    f = Fig(WW)
    S = R["systems"]
    for panel, (key, title, fmt) in enumerate([("fault_success_rate", "(a) Job success rate under injected faults", "{:.0%}"),
                                               ("mean_availability", "(b) Mean run availability under faults", "{:.2f}")]):
        x0 = 50 + panel * 310
        f.text(x0 - 50, 0, 290, 14, title, bold=True, align="left")
        ym = axes(f, x0, 22, 226, 140, 1.0, [0, 0.25, 0.5, 0.75, 1.0], "fraction")
        for k, s in enumerate(ORDER):
            v = S[s][key]
            x = x0 + 14 + k * 54
            f.box(x, ym(v), 30, 162 - ym(v), "", fill=SYS[s], stroke=SYS[s], rounded=0)
            f.text(x + 18 if key == "mean_availability" else x - 8, ym(v) - 13, 46, 12, fmt.format(v + 1e-9), fs=FS - 2,
                   align="left" if key == "mean_availability" else "center")
            f.text(x - 12, 164, 54, 22, f"{SYS_SHORT[s]} (n={S[s]['fault_runs']})", fs=FS - 3)
            if key == "mean_availability":
                lo, hi = R["table12"][s]["availability_ci_low"], R["table12"][s]["availability_ci_high"]
                cxm = x + 15
                f.line([(cxm, ym(lo)), (cxm, ym(hi))], color="#222222", width=1)
                f.line([(cxm - 5, ym(lo)), (cxm + 5, ym(lo))], color="#222222")
                f.line([(cxm - 5, ym(hi)), (cxm + 5, ym(hi))], color="#222222")
    f.text(0, 190, WW, 12, "Fault runs = executor kill + cluster outage runs in which the fault was actually injected; whiskers: 95 % bootstrap CI.", fs=FS - 1, color=GREY)
    return f


def fig23(R):
    f = Fig(WW)
    d = R["fig23"]
    tmax = max(p[0] for s in d["series"].values() for p in s)
    for panel, (idx, title, ylab) in enumerate([(1, "(a) Core utilisation U", "U"), (2, "(b) Health score H", "H")]):
        y0 = 18 + panel * 112
        f.text(0, y0 - 18, 300, 14, title, bold=True, align="left")
        x0, w, h = 50, 540, 82
        ym = axes(f, x0, y0, w, h, 1.0, [0, 0.5, 1.0], ylab)
        xm = lambda t: x0 + w * max(0, t) / tmax
        for c, col in (("A", BLUE), ("B", GREEN)):
            pts = [(xm(p[0]), ym(p[idx])) for p in d["series"][c]]
            f.line(pts, color=col, width=1.5)
        for t, col, lab in ((d["t_fault"], RED, "fault"), (d["t_action"], GREEN, "resubmitted on B")):
            f.line([(xm(t), y0), (xm(t), y0 + h)], color=col, dashed=True)
            f.text(xm(t) + 2, y0, 100, 12, lab, fs=FS - 2, color=col, align="left")
    for t in range(0, int(tmax) + 1, 20):
        f.text(50 + 540 * t / tmax - 12, 18 + 112 + 82 + 2, 24, 11, str(t), fs=FS - 2)
    f.text(50, 230, 540, 12, f"time since submission (s) — run {d['job']}", fs=FS - 1)
    legend(f, 50, 246, [("cluster A", BLUE), ("cluster B", GREEN)], per_row=2, step=100)
    return f


def fig24(R):
    f = Fig(CW)
    S = R["systems"]
    out = {s: R["cells"][f"{s}|cluster_outage"] for s in ORDER}
    raw = {"Success": {s: S[s]["fault_success_rate"] for s in ORDER},
           "Availability": {s: S[s]["mean_availability"] for s in ORDER},
           "Low downtime": {s: -S[s]["median_downtime_s"] for s in ORDER},
           "Low overhead": {s: -S[s]["clean_overhead_vs_B1"] for s in ORDER},
           "Outage handled": {s: out[s]["succeeded"] / out[s]["n"] for s in ORDER}}
    norm = {}
    for k, v in raw.items():
        lo, hi = min(v.values()), max(v.values())
        norm[k] = {s: (v[s] - lo) / (hi - lo) if hi > lo else 1.0 for s in ORDER}
    cx, cy, rr = 140, 112, 82
    axes_ = list(raw)
    ang = [-math.pi / 2 + 2 * math.pi * i / len(axes_) for i in range(len(axes_))]
    for lvl in (0.25, 0.5, 0.75, 1.0):
        pts = [(cx + rr * lvl * math.cos(a), cy + rr * lvl * math.sin(a)) for a in ang]
        f.line(pts + [pts[0]], color="#DDDDDD")
    for a, lab in zip(ang, axes_):
        f.line([(cx, cy), (cx + rr * math.cos(a), cy + rr * math.sin(a))], color="#CCCCCC")
        f.text(cx + (rr + 22) * math.cos(a) - 40, cy + (rr + 14) * math.sin(a) - 7, 80, 14, lab, fs=FS - 1)
    for s in ORDER:
        pts = [(cx + rr * max(0.03, norm[k][s]) * math.cos(a), cy + rr * max(0.03, norm[k][s]) * math.sin(a)) for k, a in zip(axes_, ang)]
        f.line(pts + [pts[0]], color=SYS[s], width=2 if s == "P_rmc" else 1.2)
    legend(f, 6, 226, [(SYS_SHORT[s], SYS[s]) for s in ORDER], per_row=2, step=136)
    f.text(0, 256, CW, 12, "min-max normalised; outer is better", fs=FS - 1, color=GREY)
    return f


def fig25(R):
    p = R["cells"]["P_rmc|cluster_outage"]
    f = Fig(CW)
    segs = [(0, 84, "normal processing", LGREEN, GREEN), (84, 126, "detect", LORANGE, ORANGE),
            (126, 176, "migrate + restart", LORANGE, ORANGE), (176, 280, "resumed on B", LGREEN, GREEN)]
    for a, b, t, fc, ec in segs:
        f.box(a, 20, b - a, 26, t, fill=fc, stroke=ec, rounded=0, fs=FS - 1)
    f.line([(84, 8), (84, 56)], color=RED, width=1.5)
    f.text(60, 0, 50, 10, "failure", fs=FS - 1, color=RED)
    f.line([(50, 8), (50, 56)], color=PURPLE, dashed=True)
    f.text(10, 0, 60, 10, "last commit", fs=FS - 1, color=PURPLE)
    f.line([(50, 62), (84, 62)], color=PURPLE)
    f.text(40, 64, 56, 12, "RPO (work)", fs=FS - 1, color=PURPLE)
    f.line([(84, 62), (176, 62)], color=RED)
    f.text(104, 64, 56, 12, "RTO", fs=FS - 1, color=RED)
    f.box(0, 84, CW, 52, f"RTO ≈ detection ({p['median_detect_s']} s measured) + stall rule (10 s) + driver start-up; "
                         "RPO ≤ τ* + one stage. Evidence: decision log, stage events, Table 13.",
          fill="#FFFFFF", stroke=GREY, fs=FS - 1, align="left")
    return f


def fig26():
    f = Fig(CW)
    tx = f.box(0, 0, 100, 24, "card transactions", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    for k, n in enumerate(["AZ 1: cluster A (primary)", "AZ 2: cluster B (standby)"]):
        x = k * 144
        f.group(x, 36, 136, 74, n, fill=LBLUE, stroke=BLUE, fs=FS - 1)
        for j, s in enumerate(["features", "model score", "alerts"]):
            f.box(x + 4 + j * 44, 60, 40, 40, s, fill="#FFFFFF", stroke=GREEN, fs=FS - 2)
    f.line([(136, 80), (144, 80)], color=RED, dashed=True, arrow=True)
    f.box(0, 124, 170, 30, "replicated object storage: features, models, commits", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    f.box(178, 124, 102, 30, "RMC-Spark controller + audit log", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    return f


def fig27():
    f = Fig(CW)
    s = f.box(0, 0, 64, 30, "machine sensors", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    i = f.box(76, 0, 64, 30, "stream ingestion", fill=LORANGE, stroke=ORANGE, fs=FS - 1)
    a = f.box(152, 0, 128, 30, "streaming anomaly job (W4 pattern)", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    b = f.box(152, 42, 128, 30, "PdM training, AI4I (W2 pattern)", fill=LGREEN, stroke=GREEN, fs=FS - 1)
    c = f.box(152, 84, 128, 26, "maintenance planning dashboard", fill="#FFFFFF", stroke=GREY, fs=FS - 1)
    f.edge(s, i)
    f.edge(i, a)
    f.edge(i, b, extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    f.edge(b, c)
    f.box(0, 124, CW, 26, "resilient multi-cluster Spark: clusters A + B, shared storage, controller", bold=True, fs=FS - 1)
    return f


def fig28(R):
    f = Fig(CW)
    C = R["cells"]
    d_p = C["P_rmc|cluster_outage"]["median_downtime_s"]
    save = {"B1_vanilla": C["B1_vanilla|cluster_outage"]["median_downtime_s"] - d_p,
            "B3_naive_ha": C["B3_naive_ha|cluster_outage"]["median_downtime_s"] - d_p}
    f.text(0, 0, CW, 14, "(a) Downtime avoided per year by RMC-Spark", bold=True, align="left")
    ym = axes(f, 50, 20, 220, 110, 8, [0, 2, 4, 6, 8], "hours / year")
    for nf in (0, 13, 26, 39, 52):
        f.text(50 + 220 * nf / 52 - 10, 131, 20, 11, str(nf), fs=FS - 2)
    f.text(50, 142, 220, 12, "cluster outages per year (N_f)", fs=FS - 1)
    for s_, col in (("B1_vanilla", SYS["B1_vanilla"]), ("B3_naive_ha", SYS["B3_naive_ha"])):
        f.line([(50, ym(0)), (270, ym(52 * save[s_] / 3600))], color=col, width=1.8)
    legend(f, 56, 22, [(f"vs B1 ({save['B1_vanilla']:.0f} s per outage, lower bound)", SYS["B1_vanilla"]),
                       (f"vs B3 ({save['B3_naive_ha']:.0f} s per outage)", SYS["B3_naive_ha"])], per_row=1, step=210)
    f.text(0, 166, CW, 14, "(b) Break-even downtime cost vs B1", bold=True, align="left")
    lg = lambda v: 186 + 110 - 110 * (math.log10(v) - 1) / 5      # 10 .. 1,000,000 per hour
    f.line([(50, 186), (50, 296), (270, 296)], color="#333333")
    for v in (10, 100, 1000, 10000, 100000, 1000000):
        f.line([(50, lg(v)), (270, lg(v))], color="#DDDDDD")
        f.text(4, lg(v) - 6, 43, 12, f"{v:,}", fs=FS - 2, align="right")
    f.text(-6, 210, 14, 70, "C_d per hour", fs=FS - 1, rotation=-90)
    for nf in (1, 13, 26, 39, 52):
        f.text(50 + 220 * nf / 52 - 10, 297, 20, 11, str(nf), fs=FS - 2)
    f.text(50, 308, 220, 12, "cluster outages per year (N_f)", fs=FS - 1)
    h = save["B1_vanilla"] / 3600
    for ce, col in ((1000, GREEN), (10000, BLUE), (100000, PURPLE)):
        pts = [(50 + 220 * nf / 52, lg(min(1e6, max(10, ce / (nf * h))))) for nf in range(1, 53)]
        f.line(pts, color=col, width=1.6)
    legend(f, 56, 324, [("C_extra = 1,000", GREEN), ("C_extra = 10,000", BLUE), ("C_extra = 100,000", PURPLE)], per_row=3, step=74)
    f.text(0, 340, CW, 12, "net benefit (Eq. 12) is positive above the curve", fs=FS - 2, color=GREY)
    return f


def fig29():
    f = Fig(CW)
    cols = [("Short term", ["threshold sensitivity", "idempotency keys"], LGREEN, GREEN),
            ("Medium term", ["replicated controller", "replicated storage"], LORANGE, ORANGE),
            ("Long term", ["multi-host / cloud runs", "geo-aware placement"], LPURPLE, PURPLE)]
    for k, (t, items, fc, ec) in enumerate(cols):
        x = k * 95
        f.text(x, 0, 90, 13, t, bold=True, color=BLUE)
        for j, it in enumerate(items):
            f.box(x, 18 + j * 40, 90, 34, it, fill=fc, stroke=ec, fs=FS - 1)
    f.box(0, 106, CW, 32, "limitations: single host · controller and MinIO single points of failure · at-least-once stages · small n",
          fill=LRED, stroke=RED, fs=FS - 1)
    return f


def fig30():
    f = Fig(CW)
    f.line([(0, 118), (280, 118)], color=BLUE, width=2, arrow=True)
    items = [("predictive signals", LBLUE, BLUE), ("Kubernetes / serverless back-ends", LGREEN, GREEN),
             ("federated clusters", LORANGE, ORANGE), ("agentic, explainable orchestration", LPURPLE, PURPLE)]
    for k, (t, fc, ec) in enumerate(items):
        x = 4 + k * 69
        y = 66 - k * 20
        f.box(x, y, 62, 40, t, fill=fc, stroke=ec, bold=True, fs=FS - 1)
        f.line([(x + 31, y + 40), (x + 31, 118)], color=ec)
    f.text(0, 124, CW, 13, "increasing autonomy, scope and scale", fs=FS - 1, italic=True, color=BLUE)
    return f


def fig31():
    f = Fig(CW)
    p = f.box(0, 0, 100, 30, "predictive models (failure, workload)", fs=FS - 1)
    a = f.box(180, 0, 100, 30, "LLM advisory agent (reads decision log)", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    c = f.box(50, 50, 180, 32, "deterministic explainable controller (health, failover, placement)", fill=LGREEN, stroke=GREEN, bold=True, fs=FS - 1)
    f.edge(p, c, "signal")
    f.edge(a, c, "proposals", dashed=True)
    for k, t in enumerate(["standalone Spark", "Kubernetes Spark", "serverless", "partner federation"]):
        b = f.box(k * 71, 104, 66, 30, t, fill="#FFFFFF", stroke=BLUE, fs=FS - 1)
        f.edge(c, b, ortho=False)
    f.box(0, 146, CW, 22, "replicated, policy-aware storage plane", fill=LPURPLE, stroke=PURPLE, fs=FS - 1)
    return f


def fig32():
    f = Fig(CW)
    data = [("Problems", ["cluster outage", "long lineage", "gray failures", "unneeded restarts", "opaque decisions"], LRED, RED),
            ("Contributions", ["C3 failover", "C2 adaptive ckpt", "C1 health signals", "progress-aware rule", "C5 explanations"], LGREEN, GREEN),
            ("Evidence", ["outage success 2/2", "overhead 0 % vs 24 %", "detection 7.6 s", "keep decisions", "decision log"], LBLUE, BLUE)]
    prev = None
    for k, (t, items, fc, ec) in enumerate(data):
        x = k * 96
        f.text(x, 0, 88, 13, t, bold=True, color=ec)
        ids = [f.box(x, 16 + j * 26, 88, 22, it, fill=fc, stroke=ec, fs=FS - 1) for j, it in enumerate(items)]
        if prev:
            for a, b in zip(prev, ids):
                f.edge(a, b, color=GREY)
        prev = ids
    f.box(0, 152, CW, 20, "rds library + open testbed + reproducible evaluation", fill=LORANGE, stroke=ORANGE, bold=True, fs=FS - 1)
    return f


NAMES = {1: "Evolution of Distributed Analytics Platforms", 2: "Resilient Data Science Ecosystem",
         3: "Failure Scenarios in Distributed Analytics", 4: "Literature Taxonomy Framework", 5: "Requirements Engineering Framework",
         6: "Resilient Multi-Cluster Spark Architecture", 7: "Layered Analytics Stack", 8: "Distributed Data Engineering Pipeline",
         9: "Spark Execution Architecture", 10: "DAG Processing Workflow", 11: "Monitoring and Observability Architecture",
         12: "Fault Detection Workflow", 13: "Fault Recovery Architecture", 14: "Failover and Recovery Workflow",
         15: "Multi-Cluster Coordination Model", 16: "Workload Orchestration Framework", 17: "Explainable Reliability Framework",
         18: "Security and Governance Architecture", 19: "Experimental Testbed Architecture", 20: "Evaluation Framework",
         21: "Fault Recovery Performance", 22: "Availability and Uptime Evaluation", 23: "Resource Utilization and Cluster Stability",
         24: "Comparative Benchmark Analysis", 25: "Business Continuity Framework", 26: "Financial Analytics Resilience Architecture",
         27: "Smart Manufacturing Analytics Platform", 28: "Business Impact Dashboard", 29: "Challenges and Limitations Roadmap",
         30: "Future Research Roadmap", 31: "Next-Generation Resilient Analytics Architecture", 32: "Research Contribution Framework"}


def main():
    R = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
    makers = {1: fig01, 2: fig02, 3: fig03, 4: fig04, 5: fig05, 6: fig06, 7: fig07, 8: fig08, 9: fig09, 10: lambda: fig10(R), 11: fig11,
              12: fig12, 13: fig13, 14: lambda: fig14(R), 15: fig15, 16: fig16, 17: fig17, 18: fig18, 19: fig19, 20: fig20,
              21: lambda: fig21(R), 22: lambda: fig22(R), 23: lambda: fig23(R), 24: lambda: fig24(R), 25: lambda: fig25(R),
              26: fig26, 27: fig27, 28: lambda: fig28(R), 29: fig29, 30: fig30, 31: fig31, 32: fig32}
    for k in sorted(makers):
        name = f"Fig {k:02d} {NAMES[k]}"
        export(makers[k](), name)
        print("exported", name)


if __name__ == "__main__":
    main()
