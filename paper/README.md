# Manuscript: Resilient Data Science Programming for Fault-Tolerant Distributed Analytics in Multi-Cluster Spark Environments

| File / folder | What it is |
|---|---|
| `RMC-Spark_Manuscript.docx` | The manuscript, filled into the official VIT consolidated template (cover, Index, List of Figures/Tables, Contributions, IEEE Access body, references, bios) |
| `RMC-Spark_Manuscript.pdf` | PDF export for reading |
| `Diagrams/` | All 32 figures at 600 DPI, named `Fig NN <Title>.png` (guideline: separate diagram folder) |
| `content/*.txt` | Manuscript source text, one file per group of sections |
| `refs/refs_keyed.json` | 127 references with metadata from OpenAlex (all real records, none retracted) |
| `make_figures.py` | Regenerates `Diagrams/` |
| `build_paper.py` | Rebuilds the .docx from `content/`, `refs/` and `Diagrams/` into the template |
| `build_report.txt` | Counts produced by the last build: figures, tables, equations, references, words per section and per member |

## Rebuild

Run with the Anaconda Python, which has matplotlib, lxml and Pillow:

```bash
python paper/make_figures.py
```

```bash
python paper/build_paper.py --template "C:/Users/msi/Downloads/3_Consolidated_Template.docx"
```

After a rebuild, open the .docx in Word and press `Ctrl+A`, `F9` to refresh the page numbers in the Index, List of Figures and List of Tables. The page numbers are PAGEREF fields.

## Before submission

1. **Run the experiments** (repository README, Steps 6–8). Then replace every yellow-highlighted `[[...]]` placeholder (about 120) with measured values:
   - Sections XV–XVII and XIX
   - Tables 11–15
   - Figures 21–24 and 28: copy the PNGs from `results/report/` into `Diagrams/` using the same file names, then rebuild
2. **Fill in personal details:** student names, VIT e-mails and bios (search for `[[Student name]]` and `[[STUDENT NAME]]`), and the names on the cover page boxes ("Name").
3. **Add the GitHub link** in the Data Availability section.
4. **Delete the AUTHOR NOTE** at the start of Section XV.
5. **Run a similarity check.** The guideline requires ≤ 10 %; the text is original, but check it anyway.
6. **Redraw diagrams in draw.io (optional).** The guidelines say diagrams should be redrawn with draw.io. The figures here are generated programmatically and are original, but if your faculty insists on draw.io, use them as the layout reference.
7. **Word count.** The plan's per-section minimums add up to about 18.9k words, but the plan's total is 10–15k. The text is about 16.6k words of prose; the results sections will grow when real numbers are added. Confirm the limit with your faculty.

Equations are native Word (OMML) equations, so they are editable in Word's equation editor. Keep the file as .docx: saving as legacy .doc turns the equations into pictures.
