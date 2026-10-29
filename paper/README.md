# Manuscript build scripts

The finished manuscript (.docx/.doc/.pdf) and the 600-DPI diagrams are part of the submission package,
not of this repository. This folder holds the sources and scripts that produce them.

| File / folder | What it is |
|---|---|
| `content/*.txt` | Manuscript source text, one file per group of sections |
| `refs/refs_keyed.json` | The 127 references with metadata (all verified against Crossref/OpenAlex) |
| `results_data.py` | Computes every measured value used in the paper from `results/raw/` into `results.json` (runs whose fault never fired are excluded) |
| `drawio_figures.py` | Builds all 32 figures as editable draw.io diagrams and exports them as 600-DPI PNGs (needs draw.io Desktop) into `paper/Diagrams/` |
| `build_paper.py` | Fills `content/`, `refs/` and `Diagrams/` into the official VIT consolidated template and writes the .docx |
| `check_words.py` | Checks every section's word count against the plan's ranges and the 15,000-word total |
| `make_figures.py`, `make_fig28.py` | Older matplotlib versions of the figures (no longer used) |
| `make_guide.js`, `make_impl_plan.js` | Generate the research-guide and implementation-plan documents |

## Rebuild

```bash
python paper/results_data.py
```

```bash
python paper/drawio_figures.py
```

```bash
python paper/build_paper.py --template path/to/3_Consolidated_Template.docx
```

After a rebuild, open the .docx in Word and press `Ctrl+A`, `F9` to refresh the page numbers in the Index,
List of Figures and List of Tables (they are PAGEREF fields).

Equations are native Word (OMML) equations, editable in Word's equation editor. Keep the file as .docx:
saving as legacy .doc turns the equations into pictures.
