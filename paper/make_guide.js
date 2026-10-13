// Builds "Research_Guide_and_Section_Instructions.docx" from the team's section plan (26FSPDSCPMID4098.pdf),
// the literature collected for the manuscript, and the RMC-Spark implementation.
// Run: NODE_PATH=%APPDATA%/npm/node_modules node paper/make_guide.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  AlignmentType, HeadingLevel, LevelFormat, PageBreak, Footer, PageNumber, TableOfContents, PageOrientation,
} = require("docx");

const OUT = path.join(__dirname, "Research_Guide_and_Section_Instructions.docx");
const BLUE = "00629B", LBLUE = "E3F0F8", LGREY = "F2F2F2", LGREEN = "E6F4EC", LORANGE = "FDF1DC", LRED = "FBE5E3";
const PAGE_W = 11906, MARGIN = 1134, CONTENT_W = PAGE_W - 2 * MARGIN; // A4, 2 cm margins -> 9638 dxa

// ------------------------------------------------------------------ helpers
const runs = (text, opts = {}) => {
  // **bold** segments
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(s =>
    s.startsWith("**") ? new TextRun({ text: s.slice(2, -2), bold: true, ...opts }) : new TextRun({ text: s, ...opts }));
};
const P = (text, opts = {}) => new Paragraph({ children: runs(text, opts.run || {}), spacing: { after: 120 }, ...opts.para });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true });
const H1n = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (text, level = 0) => new Paragraph({ numbering: { reference: "bullets", level }, children: runs(text), spacing: { after: 60 } });
const N = (text, ref = "steps") => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(text), spacing: { after: 60 } });
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };

function table(header, rows, pct, opts = {}) {
  const widths = pct.map(p => Math.floor(CONTENT_W * p / 100));
  widths[widths.length - 1] = CONTENT_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const cell = (t, i, hdr, fill) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    shading: { fill: hdr ? BLUE : (fill || "FFFFFF"), type: ShadingType.CLEAR, color: "auto" },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: String(t).split("\n").map(line => new Paragraph({
      children: runs(line, { size: opts.size || 18, color: hdr ? "FFFFFF" : undefined, bold: hdr || undefined }),
    })),
  });
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r, ri) => new TableRow({ children: r.map((c, i) => cell(c, i, false, opts.firstColFill && i === 0 ? opts.firstColFill : (ri % 2 ? LGREY : undefined))) }))],
  });
}
function kv(pairs, pct = [26, 74], fill = LBLUE) {
  const widths = pct.map(p => Math.floor(CONTENT_W * p / 100));
  widths[1] = CONTENT_W - widths[0];
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: pairs.map(([k, v]) => new TableRow({ children: [
      new TableCell({ borders, width: { size: widths[0], type: WidthType.DXA }, shading: { fill, type: ShadingType.CLEAR, color: "auto" },
        margins: { top: 60, bottom: 60, left: 100, right: 100 }, children: [new Paragraph({ children: [new TextRun({ text: k, bold: true, size: 18 })] })] }),
      new TableCell({ borders, width: { size: widths[1], type: WidthType.DXA }, margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: (Array.isArray(v) ? v : String(v).split("\n")).map(line => new Paragraph({ children: runs(line, { size: 18 }) })) }),
    ] })),
  });
}
const gap = () => new Paragraph({ children: [], spacing: { after: 120 } });

// ------------------------------------------------------------------ data: sections of the plan PDF
// plan: content focus + visuals + word count from 26FSPDSCPMID4098.pdf; cur: words in current manuscript
const S = [
  { n: "—", t: "Executive Summary and Abstract", owner: "26MML0015", plan: "450–750", cur: 490,
    focus: "Summarize the challenges of distributed analytics resilience, proposed fault-tolerant Spark architecture, experimental outcomes, and industrial significance.",
    visuals: "Table 1: Executive Summary of Contributions and Outcomes",
    write: ["Abstract: one paragraph, 150–250 words, no citations or equations (IEEE rule): problem → RMC-Spark (C1–C5 + rds) → implementation → evaluation → significance.",
      "Executive summary: why Spark's single-cluster fault tolerance is not enough; what the rds library and controller do; Table 1 with status of each contribution.",
      "After experiments: replace the generic 'measured results are reported in Section XV' sentence with the 2–3 headline numbers."],
    refs: "[1]–[6] (fraud/maintenance motivation, Spark engine, survey of fault-tolerant analytics)",
    ours: "Contributions C1–C5, rds library, test suite (56 tests), evaluation harness.", todo: "Insert headline measured results." },
  { n: "—", t: "Keywords", owner: "26MML0054", plan: "20–40", cur: 17,
    focus: "Distributed Analytics, Apache Spark, Fault Tolerance, Multi-Cluster Computing, Resilient Data Science, High Availability, Data Engineering, Cloud Analytics.",
    visuals: "No visuals required", write: ["Use exactly the 8 keywords of the plan, in alphabetical order (IEEE 'INDEX TERMS')."],
    refs: "—", ours: "—", todo: "Done." },
  { n: "1", t: "Introduction", owner: "26MML0047", plan: "800–1200", cur: 867,
    focus: "Evolution of distributed analytics, Spark ecosystems, cloud-native data science, fault tolerance requirements, motivation for resilient analytics programming.",
    visuals: "Figure 1: Evolution of Distributed Analytics Platforms\nFigure 2: Resilient Data Science Ecosystem",
    write: ["A. Evolution: MapReduce → YARN → RDD lineage → Spark SQL/Streaming/Flink → Kubernetes, serverless, lakehouse (Fig. 1).",
      "B. Ecosystem: programs + platform + storage + the three teams who build/operate them (Fig. 2).",
      "C. Why fault tolerance got harder: long lineage, gray failures, several clusters per organisation.",
      "D. Motivation and numbered contributions (1)–(5); paper organisation paragraph."],
    refs: "[3]–[27] incl. MapReduce [7], YARN [8], RDD [5], Spark [3], Flink [11], Borg/Kubernetes [13][14], gray failure [24], multi-cloud [25]",
    ours: "Contribution list = the five components + rds + open testbed.", todo: "Done (meets minimum)." },
  { n: "2", t: "Problem Statement", owner: "26MML0006", plan: "400–700", cur: 501,
    focus: "Node failures, cluster outages, workload imbalance, data loss, performance degradation, operational downtime.",
    visuals: "Figure 3: Failure Scenarios in Distributed Analytics\nTable 2: Research Challenges and Gaps",
    write: ["Classify failures by blast radius: task, node, gray, cluster (Fig. 3) and who reacts first in standard Spark.",
      "List the five concrete problems from the plan (outage, imbalance, data loss, degradation, downtime).",
      "Formal model: job = stages s1..sn, cluster MTBF Mk; objectives (completion probability, expected time, overhead, explainability).",
      "One-sentence research question + Table 2 (challenge / state of practice / gap)."],
    refs: "[5][24][30]–[38] (node/disk failure prediction, straggler survey, lineage, SLOs)",
    ours: "Each gap in Table 2 maps to a component (see Part D of this guide).", todo: "Done." },
  { n: "3", t: "Background and Literature Review", owner: "26MML0047", plan: "1500–2500", cur: 1491,
    focus: "Spark fault tolerance, distributed systems resilience, cluster orchestration, data replication, workload recovery, high-availability frameworks.",
    visuals: "Figure 4: Literature Taxonomy Framework\nTable 3: Comparative Analysis of Existing Approaches (core table)",
    write: ["Organise by the 6 branches of Fig. 4: engine-level recovery, checkpoint optimisation, recovery benchmarks, stragglers & gray failures, prediction & AIOps, orchestration across clusters/clouds, resilience engineering; plus data platforms and a synthesis.",
      "For each paper: one sentence on what it does + one on its limitation relative to our problem. Summarise in your own words (similarity ≤ 10 %).",
      "Table 3: 13 approaches × properties (cross-cluster recovery, adaptive checkpoint, gray-failure aware, explainable, fault injection, engine).",
      "End with the positioning paragraph: no reviewed approach covers all five properties."],
    refs: "97 references cited here; key ones: [5][23][27][39]–[49][52]–[59][28][62][65][76][78][90][95]",
    ours: "RMC-Spark row of Table 3 = Yes on all five properties.", todo: "About 10 words short of the minimum — add one sentence when you revise." },
  { n: "4", t: "Requirements Analysis for Resilient Analytics Systems", owner: "26MML0006", plan: "600–1000", cur: 547,
    focus: "Scalability, availability, recoverability, reliability, interoperability, governance, operational continuity requirements.",
    visuals: "Figure 5: Requirements Engineering Framework\nTable 4: Functional and Non-Functional Requirements Matrix",
    write: ["Fig. 5: stakeholders → requirements → components → verification (traceability).",
      "Sub-sections: Scalability & availability; Recoverability & reliability; Interoperability, governance & continuity.",
      "Table 4: F1–F7 functional, N1–N5 non-functional, each with component and verification method."],
    refs: "[29][38][109][110][112][113]", ours: "Every requirement is verified by a unit test, the simulation, or an experiment.",
    todo: "About 50 words short — add a short paragraph on requirement prioritisation (MoSCoW) if needed." },
  { n: "5", t: "Multi-Cluster Spark Analytics Architecture", owner: "26MML0015", plan: "1000–1500", cur: 963,
    focus: "Overall architecture integrating multiple Spark clusters, data engineering pipelines, monitoring services, failover mechanisms, orchestration components.",
    visuals: "Figure 6: Multi-Cluster Spark Architecture (CORE FIGURE)\nFigure 7: Layered Analytics Stack",
    write: ["Four design principles: unmodified engine; jobs separated from clusters; act on evidence of harm; explain every action.",
      "Fig. 6 walkthrough: clusters A/B, MinIO, Prometheus/Grafana, controller hosting the drivers (client mode) — explain why driver placement is the key decision.",
      "Component interactions + the outage sequence in words; layered stack (Fig. 7); failure domains & assumptions; deployment model (testbed vs production)."],
    refs: "[24][25][30][65][90] + observability [99][100]",
    ours: "docker-compose.yml, controller/core.py; README §1.", todo: "Slightly below minimum; fine." },
  { n: "6", t: "Distributed Data Engineering Layer", owner: "26MML0006", plan: "1000–1500", cur: 980,
    focus: "Ingestion, transformation, metadata management, schema evolution, data partitioning, storage management across clusters.",
    visuals: "Figure 8: Distributed Data Engineering Pipeline\nTable 5: Data Engineering Components and Responsibilities",
    write: ["Buckets data / checkpoints / results; synthetic generator (seeded) + public datasets (NYC TLC, AI4I 2020, ULB credit card).",
      "Resilient stages and the commit-marker protocol (data first, marker last; never read half-written output).",
      "Metadata (markers with sequence numbers, linear-chain skipping), schema evolution policy, streaming path, partitioning (16 partitions, AQE), data quality."],
    refs: "[17][18][104]–[113]", ours: "rds/stage.py, jobs/datagen.py, jobs/etl_taxi.py, datasets/README.md", todo: "Done." },
  { n: "7", t: "Spark Processing and Execution Layer", owner: "26MML0006", plan: "1200–1800", cur: 943,
    focus: "Spark execution model, RDD lineage, DAG scheduling, task execution, resource allocation, distributed processing flow.",
    visuals: "Figure 9: Spark Execution Architecture\nFigure 10: DAG Processing Workflow\nEquation: Resource Utilization Function (Eq. 1)",
    write: ["Standalone master/worker model; driver in client mode in the controller; resource settings (512 MB driver, 1 core / 576 MB executors, 4 cores per job).",
      "Narrow vs wide dependencies, stage boundaries, how a committed resilient stage cuts the lineage (Fig. 10).",
      "Built-in fault tolerance (task.maxFailures 4, 60 s network timeout, speculation in P); Eq. 1 utilisation U; processing flow; interaction of built-in and external recovery."],
    refs: "[3][5][9][19][23][55][101][103]", ours: "docker/spark-defaults.conf, controller/jobs.py (spark-submit), analysis/metrics.py (U)",
    todo: "About 250 words short — after experiments, add a paragraph describing the real DAG/stage timings from the Spark UI." },
  { n: "8", t: "Fault Detection and Monitoring Framework", owner: "26MML0054", plan: "1000–1500", cur: 1003,
    focus: "Cluster monitoring, anomaly detection, health assessment, workload diagnostics, early-failure detection.",
    visuals: "Figure 11: Monitoring and Observability Architecture\nFigure 12: Fault Detection Workflow\nTable 6: Monitoring Metrics and Thresholds (CORE TABLE)",
    write: ["Two observation paths: direct probes for decisions (2 s), Prometheus/Grafana for operators (5 s).",
      "Five signals; EWMA z-score (Eq. 2); additive health score H (Eq. 3) with weights; 'zero workers' override.",
      "State machine HEALTHY/SUSPECT/FAILED with hysteresis (Fig. 12); why delay or stall alone only gives SUSPECT; calibration and false alarms.",
      "Table 6 must contain the exact values from configs/clusters.yaml."],
    refs: "[24][30][35][65][67][68][73][99][100][102]", ours: "controller/monitor.py, anomaly.py, health.py, statemachine.py; tests/test_detection.py", todo: "Done." },
  { n: "9", t: "Fault-Tolerant Recovery and Resilience Layer", owner: "26MML0015", plan: "1200–1800", cur: 1019,
    focus: "Checkpointing, replication, lineage recovery, failover mechanisms, workload migration, self-healing.",
    visuals: "Figure 13: Fault Recovery Architecture (+ (b) τ* vs MTBF plot)\nFigure 14: Failover and Recovery Workflow",
    write: ["Three recovery levels: task (Spark), attempt (retry on same cluster), cluster (migrate).",
      "Adaptive checkpointing: Young/Daly τ* (Eq. 4), expected lost work (Eq. 5), online MTBF estimate (Eq. 6).",
      "Stage restoration, progress-aware failover rules (Table 16 in appendix), self-healing, correctness-of-resumption argument."],
    refs: "[5][20][23][27][39][43]–[49]", ours: "rds/policy.py, rds/stage.py, controller/jobs.py; tests/test_policy.py, test_controller_sim.py",
    todo: "Add measured τ* range and checkpoint counts after experiments." },
  { n: "10", t: "Multi-Cluster Coordination and Orchestration Layer", owner: "26MML0015", plan: "1000–1500", cur: 799,
    focus: "Cluster synchronization, workload balancing, orchestration policies, service discovery, coordination protocols.",
    visuals: "Figure 15: Multi-Cluster Coordination Model\nFigure 16: Workload Orchestration Framework",
    write: ["Centralised, asynchronous coordination through shared state (no cluster-to-cluster messages).",
      "Cluster registry as service discovery; placement cost J (Eq. 7) with α=0.4, β=0.5, γ=0.1; why a weighted sum rather than a learned scheduler.",
      "5-step coordination protocol; synchronisation & consistency (idempotent writes, fencing); scaling to more clusters."],
    refs: "[14][28][78][84][86][87][90]", ours: "controller/orchestrator.py, configs/clusters.yaml; tests (placement)",
    todo: "About 200 words short — add a worked placement example with three clusters, or a paragraph on the effect of the weights." },
  { n: "11", t: "Explainability and Reliability Assessment Layer", owner: "26MML0054", plan: "1000–1500", cur: 846,
    focus: "Explainability of recovery decisions, root-cause analysis, reliability scoring, operational transparency.",
    visuals: "Figure 17: Explainable Reliability Framework\nTable 7: Reliability Assessment Indicators\nEquation: Reliability Score Model (Eq. 8)",
    write: ["Decision log contents (transition, failover, keep, job end) with per-signal contributions.",
      "Root-cause reading of the log; reliability score R (Eq. 8) and its four indicators (Table 7).",
      "Worked example of one outage (four log records); limits of additive explanations; operational transparency (API, CLI, Grafana)."],
    refs: "[30][65][74][75][93][94]+", ours: "controller/decisions.py, reliability.py, api.py", todo: "After experiments, paste a real excerpt of decisions.jsonl." },
  { n: "12", t: "Security, Governance, and Compliance Layer", owner: "26MML0047", plan: "800–1200", cur: 651,
    focus: "Security controls, access management, disaster recovery policies, auditing, governance monitoring, compliance.",
    visuals: "Figure 18: Security and Governance Architecture\nTable 8: Governance and Compliance Controls",
    write: ["Be honest: separate IMPLEMENTED controls (private network, storage credentials, decision log, per-job namespaces, provenance markers) from DESIGNED ones (Spark auth, TLS, bucket policies, RBAC, non-root, secrets).",
      "Threat model (rogue submission, forged checkpoints, steered failover); access & auditing; DR policies (RTO/RPO); jurisdiction-aware placement."],
    refs: "[95][112][113][118][119]", ours: "Table 8 status column.", todo: "About 150 words short — optional: actually enable spark.authenticate and move it to 'implemented'." },
  { n: "13", t: "Experimental Setup", owner: "26MML0006", plan: "700–1200", cur: 782,
    focus: "Datasets, Spark clusters, cloud infrastructure, network environment, benchmark workloads, evaluation configurations.",
    visuals: "Figure 19: Experimental Testbed Architecture\nTable 9: Experimental Configuration Details (CORE TABLE)",
    write: ["Host (12 CPUs, 16 GB, Docker/WSL2 12 GB), container limits, Spark 3.5.3 image.",
      "Workloads W1–W4 + 2 case studies; 9 fault types (transient vs persistent); 5 configurations B1, B2, B3, A1, P.",
      "Procedure: shuffled runs, raw files, runner errors recorded. Update Table 9 if you change repetitions or fault times."],
    refs: "[19][53][95][96]", ours: "experiments/configs/full.yaml, chaos/inject.py, results/raw/full/experiment.json", todo: "Fill measured clean runtimes and the final fault_at_s values." },
  { n: "14", t: "Evaluation Metrics", owner: "26MML0054", plan: "500–800", cur: 505,
    focus: "Fault tolerance metrics, recovery time, availability, throughput, latency, scalability, resource efficiency, reliability indicators.",
    visuals: "Figure 20: Evaluation Framework\nTable 10: Metrics Definition Matrix",
    write: ["Availability (Eq. 9), recovery time (Eq. 10), overhead (Eq. 11), utilisation (Eq. 1), streaming recovery rule (≥ 85 % for 40 s, as Vogel et al.).",
      "Statistics: Mann-Whitney U, Cliff's δ, bootstrap CI; metric validity limitations."],
    refs: "[29][53][54][94]", ours: "analysis/metrics.py, analysis/stats.py", todo: "Done." },
  { n: "15", t: "Results and Findings", owner: "26MML0054", plan: "1200–2000", cur: 668,
    focus: "Recovery performance, cluster resilience, workload continuity, throughput stability, system efficiency, operational availability.",
    visuals: "Figure 21: Fault Recovery Performance (CORE)\nFigure 22: Availability Analysis (CORE)\nFigure 23: Resource Utilization Trends (CORE)\nTable 11: Experimental Results Summary (CORE)",
    write: ["Hypotheses H1–H5 are already written — for each, report the measured value, p-value, Cliff's δ and say SUPPORTED / NOT SUPPORTED.",
      "Replace every [[...]] with numbers from results/report (Table 11 CSV, runs_enriched.csv).",
      "Copy Figs 21–23 PNGs from results/report into paper/Diagrams with the same names and rebuild.",
      "Negative results are fine — explain them (e.g., overhead higher than expected)."],
    refs: "[10][52][53]", ours: "analysis/report.py output", todo: "BLOCKED until experiments run. Expected to reach ~1200+ words when filled." },
  { n: "16", t: "Comparative Analysis", owner: "26MML0006", plan: "800–1200", cur: 505,
    focus: "Compare against standard Spark deployments, single-cluster architectures, Kubernetes-based analytics, high-availability platforms.",
    visuals: "Figure 24: Comparative Radar Chart (CORE)\nTable 12: Comparative Benchmark Analysis (CORE)",
    write: ["Table 12 upper half (capabilities by design) is done; fill the measured lower half.",
      "Ablation logic: B1 vs B2, B1 vs B3, B3 vs A1, A1 vs P — state each measured difference.",
      "Kubernetes and published benchmarks: compare qualitatively only (different hardware) — never put Vogel et al.'s numbers in your table."],
    refs: "[52][53][78][79][106]", ours: "Table 12 from report.py; Fig 24 radar", todo: "BLOCKED until experiments; optional B4 Kubernetes run." },
  { n: "17", t: "Reliability and Business Continuity Assessment", owner: "26MML0047", plan: "700–1000", cur: 534,
    focus: "Resilience, disaster recovery readiness, business continuity, operational reliability, trustworthiness.",
    visuals: "Figure 25: Business Continuity Framework\nTable 13: Reliability and Continuity Assessment Matrix",
    write: ["RTO/RPO for analytics jobs (Fig. 25); design-derived bounds (≈16 s + driver start-up; ≤ τ* + one stage).",
      "Measured columns of Table 13 (max downtime, mean recomputed work); final R of clusters A and B; DR readiness questions; trustworthiness."],
    refs: "[38][94][95][99]", ours: "decision log, stage events", todo: "Fill measured columns and driver start-up time." },
  { n: "18", t: "Industry Use Cases and Case Study Evaluation", owner: "26MML0047", plan: "800–1500", cur: 671,
    focus: "Applications in banking, healthcare, telecommunications, manufacturing, smart cities, cybersecurity.",
    visuals: "Figure 26: Financial Analytics Resilience Architecture\nFigure 27: Smart Manufacturing Analytics Platform\nTable 14: Industry Use Cases Matrix",
    write: ["One sub-section per domain with its resilience need and the RMC-Spark mechanism that meets it.",
      "Two REAL case studies: case_fraud (ULB credit card) and case_maintenance (AI4I 2020) — run each with a cluster outage, report completion, restored stages, and AUC equal to the uninterrupted run.",
      "Case-study protocol and lessons for adoption are written."],
    refs: "[120]–[127]", ours: "controller/workloads.py (case_fraud, case_maintenance), scripts/download_data.py", todo: "Run the 2 case studies and fill [[...]]." },
  { n: "19", t: "Business Impact Assessment", owner: "26MML0054", plan: "500–1000", cur: 344,
    focus: "Downtime reduction, resource savings, performance improvement, operational resilience, ROI.",
    visuals: "Figure 28: Business Impact Dashboard\nTable 15: Cost-Benefit Analysis",
    write: ["Net benefit model ΔB = N_f (D_base − D_rmc) C_d − C_extra (Eq. 12).",
      "D_base, D_rmc, ΔW, O come from experiments; N_f, C_d, C_extra are organisation-specific — state assumptions and their source.",
      "Draw Fig. 28 as a sensitivity plot of ΔB over N_f and C_d after experiments."],
    refs: "[38]", ours: "analysis results", todo: "BLOCKED; will exceed 500 words with the sensitivity discussion." },
  { n: "20", t: "Challenges and Limitations", owner: "26MML0015", plan: "600–1000", cur: 485,
    focus: "Cross-cluster synchronization issues, latency overhead, network bottlenecks, operational complexity, deployment costs.",
    visuals: "Figure 29: Challenges and Limitations Roadmap",
    write: ["Controller & MinIO single points of failure; at-least-once stage execution; overhead & geo latency; operational complexity; determinism & data size; threats to validity (single host, small data, 3 reps)."],
    refs: "[53][90][91]", ours: "README §13 limitations", todo: "Add measured overhead numbers; ~100 words to add." },
  { n: "21", t: "Future Research Directions", owner: "26MML0054", plan: "600–1200", cur: 399,
    focus: "Autonomous recovery systems, AI-driven fault prediction, federated cluster management, self-healing platforms, agentic orchestration.",
    visuals: "Figure 30: Future Research Roadmap\nFigure 31: Next-Generation Resilient Analytics Architecture",
    write: ["Predictive signals (failure/workload predictors feeding H); federated clusters; Kubernetes/serverless back-ends; LLM advisory agent over the decision log; learned checkpoint policies; formal verification; energy/cost-aware placement; threshold calibration."],
    refs: "[35][44][62][66][84][108][109][114]+", ours: "—", todo: "About 200 words short — expand one direction (e.g., Kubernetes back-end) into a paragraph." },
  { n: "22", t: "Conclusion", owner: "26MML0015", plan: "500–800", cur: 392,
    focus: "Summarize contributions, findings, practical implications, future opportunities.",
    visuals: "Figure 32: Research Contribution Framework",
    write: ["Restate problem and contributions (Fig. 32); 2–3 measured findings + hypotheses outcome; practical implication; lessons learned; future work."],
    refs: "—", ours: "—", todo: "Insert findings → will reach 500 words." },
  { n: "—", t: "References", owner: "All (26MML0047 lead)", plan: "80–140 (plan); ≥ 30–50 (guidelines)", cur: "127 refs",
    focus: "Research literature on Spark, distributed systems, fault tolerance, cloud computing, resiliency engineering, data science platforms.",
    visuals: "No visuals required",
    write: ["IEEE numeric style, numbered in order of first citation; cite as [1] or [1][3][5] at the end of the sentence (guideline format).",
      "All 127 come from OpenAlex records; none retracted; 114 journal / 13 conference; 108 from 2020–2025.",
      "Do not add any reference you have not opened; re-run the citation check if you add new ones."],
    refs: "paper/refs/refs_keyed.json", ours: "build_paper.py numbers them automatically", todo: "Done." },
  { n: "—", t: "Appendix (Optional)", owner: "26MML0006", plan: "500–2000", cur: 146,
    focus: "Cluster configurations, recovery algorithms, benchmark workloads, Spark tuning parameters, monitoring rules, supplementary results.",
    visuals: "Additional figures and tables as required (Table 16: Recovery rules per mode)",
    write: ["Add: full spark-defaults.conf, clusters.yaml, pseudo-code of the control loop and of a resilient stage, per-workload result tables."],
    refs: "—", ours: "configs/, docker/, controller/core.py", todo: "Optional: expand to ~500 words with pseudo-code + per-workload results." },
];

// ------------------------------------------------------------------ existing research themes
const THEMES = [
  { t: "Fault tolerance inside the Spark engine", refs: "[5] RDD lineage (Zaharia 2012); [39] RCMP (Dinu 2014); [23] Lineage checkpoint (Kweun 2020); [27] Write-ahead lineage (Wang 2024); [40] cache recovery (Li 2021); [41] LT-code caching (2024); [42] GraphX fault tolerance (He 2025); [6] systematic survey (Isukapalli 2024); [4] Spark ecosystem survey (Tang 2020)",
    good: "Cheap, transparent recovery of lost partitions and tasks; techniques to shorten long lineage.",
    missing: "All assume the cluster survives. None resumes a job on a different cluster after an outage." },
  { t: "Checkpoint interval optimisation", refs: "[43] Young 1974; [44] Daly 2006; [45] En-CHORE online MTBF (Sigdel 2020); [46][47] utilisation-optimal stream checkpoints (Jayasekara 2020/2021); [48] Flink interval (Zhang 2021); [49] FATM failure-aware (Akber 2021); [50] incremental checkpointing; [51] convergence-aware (Li 2024)",
    good: "Solid theory for when to checkpoint given checkpoint cost C and MTBF M; adaptive variants exist.",
    missing: "Applied to HPC jobs or stream operators, not to data science pipeline stages; MTBF not shared across clusters." },
  { t: "Fault-recovery benchmarks", refs: "[52] van Dongen 2021 (IEEE Access, 4 stream frameworks); [53] Vogel 2024 (ACM DEBS, Kubernetes + chaos); [54] PGVal (Tahir 2024, PVLDB); [19] stream processing survey (Fragkoulis 2023)",
    good: "Rigorous measurement of downtime, recovery time and data loss under injected faults.",
    missing: "Single-cluster only; whole-cluster loss not tested; no comparison of recovery strategies on the same engine." },
  { t: "Stragglers and gray failures", refs: "[55] LATE (2008); [56] Mantri (2010); [57] Hawkeye RL (Du 2020); [58] ANN stragglers (2020); [34] straggler survey (Bawankule 2022); [59] Hone (Li 2021); [24] Gray Failure (Huang 2017)",
    good: "Speculation and learned straggler identification; the gray-failure concept explains silent degradation.",
    missing: "Not combined with cluster-level failover; most detectors look only at one side (cluster or job)." },
  { t: "Failure prediction and AIOps", refs: "[35] Bi-LSTM task failure (Gao 2020); [60] ML vs DL predictors (Asmawi 2022); [61] ML job failures (2023); [62] proactive failure-aware scheduling (Alahmad 2021); [63] OFP-TM; [30][31] node failure prediction; [32][33] disk failure; [64] workload prediction; [65] AIOps survey (Notaro 2021); [66][67] MLOps/LLM AIOps; [68]–[77] anomaly detection & root-cause analysis",
    good: "Accurate prediction and detection on large traces; rich anomaly/RCA techniques.",
    missing: "Outputs rarely trigger concrete recovery of analytics jobs; models are opaque — operators need interpretable decisions [30]." },
  { t: "Orchestration across clusters and clouds", refs: "[13] Borg; [14] Borg/Omega/Kubernetes; [78]–[80] Kubernetes scheduling surveys; [81][82] container orchestration; [83] HPC containers; [25] multi-cloud orchestration review; [84] multi-cloud scheduling (Zhu 2021); [85]–[91] geo-distributed analytics; [28] RL multi-cloud Spark scheduler with micro-checkpointing (Raj 2026) — CLOSEST WORK",
    good: "Placement, scheduling and data movement across sites and clouds; pod restarts inside one Kubernetes cluster.",
    missing: "Little support for continuing a running analytics job after its cluster disappears; learned schedulers explain little." },
  { t: "Cloud fault tolerance and resilience engineering", refs: "[92]–[94] proactive FT, reliability & availability models; [36][37][22] FT surveys; [95] Chaos Engineering (Basiri 2016); [96]–[99] chaos for security, Docker, digital twins, MLR 2025; [29][38] SLO/SLA",
    good: "Availability modelling and controlled fault experiments are mature practice.",
    missing: "Not specialised to resumable analytics pipelines; rarely produce reproducible, open testbeds for Spark." },
];

// ------------------------------------------------------------------ build document
const children = [];
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1800, after: 200 },
  children: [new TextRun({ text: "Research Guide and Section Instructions", bold: true, size: 44, color: BLUE })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
  children: [new TextRun({ text: "Resilient Data Science Programming for Fault-Tolerant Distributed Analytics in Multi-Cluster Spark Environments", size: 28, italics: true })] }));
children.push(kv([
  ["Team ID", "26FSPDSCPMID4098"], ["Members", "26MML0054, 26MML0006, 26MML0047, 26MML0015 (PoC)"],
  ["Course", "Programming for Data Science (MACSE502), SCOPE, VIT"], ["Guide", "Dr. M. Rajasekhara Babu"],
  ["Based on", "Section planning table 26FSPDSCPMID4098.pdf, Manuscript Guidelines, and the RMC-Spark implementation"],
  ["Companion files", "paper/RMC-Spark_Manuscript.docx (manuscript), paper/Diagrams/ (figures), rmc-spark/README.md (implementation)"],
  ["Date", "October 2026"],
]));
children.push(gap());
children.push(P("**How to use this file.** The Project Overview explains the project in plain words. Part A summarises what existing research already does and where it stops. Part B states the gap. Part C explains how our system, RMC-Spark, solves it. Part D is the instruction sheet for every section of the plan: what to write, which references to cite, which figures and tables are required, the word target, the owner and what is still missing. Parts E and F are checklists and the step-by-step plan to finish. Reference numbers [n] are the same as in the manuscript."));
children.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));

// ---------------- Project overview
children.push(H1("Project Overview — What Is This Project?"));
children.push(P("This project is a research paper plus a working system for **Programming for Data Science (MACSE502)** at VIT (Team 26FSPDSCPMID4098, guide Dr. M. Rajasekhara Babu)."));
children.push(P("**Title:** Resilient Data Science Programming for Fault-Tolerant Distributed Analytics in Multi-Cluster Spark Environments"));
children.push(H2("The problem"));
children.push(P("Apache Spark is the standard engine for big-data analytics. If a single machine or task fails, Spark recovers on its own. But if the whole cluster goes down (master crash, network split, data-centre outage), every job on it dies and someone has to rerun it from the start. Long pipelines, such as ML training, can lose hours of work, and today's tools rarely explain why they acted."));
children.push(H2("Our solution: RMC-Spark"));
children.push(P("A layer that sits above two or more ordinary Spark clusters:"));
children.push(...[
  "**Health monitor:** checks every cluster every 2 seconds and gives it a health score. A cluster is marked FAILED only on strong evidence.",
  "**Resumable pipeline stages (the rds library):** each step of a PySpark pipeline saves its result to shared storage. The timing follows a checkpoint formula (Young/Daly), so the work lost in a failure stays small.",
  "**Smart failover:** if a cluster dies and the job has stopped making progress, the job moves to the healthy cluster. There it continues from the last saved step instead of starting over.",
  "**Placement:** picks the best cluster from its load and health.",
  "**Explainability:** every decision is logged with its reason, and each cluster gets a reliability score.",
].map(t => N(t, "overview")));
children.push(new Paragraph({ spacing: { before: 120, after: 120 }, shading: { fill: LBLUE, type: ShadingType.CLEAR, color: "auto" },
  children: runs("**In one line:** when a Spark cluster crashes, the job moves to another cluster and carries on from where it stopped, and the system explains why.") }));
children.push(H2("How we prove it"));
children.push(P("The whole system runs on a laptop in Docker: 2 Spark clusters, MinIO storage, Prometheus/Grafana, and the controller. We deliberately break it with 9 kinds of faults, such as killing a cluster or slowing the network. Then we compare five setups, from plain Spark through simple failover to RMC-Spark, on four workloads: ETL, machine learning, iterative PageRank and streaming."));

// ---------------- Part A
children.push(H1("Part A — Existing Research (State of the Art)"));
children.push(P("The literature used in the manuscript (127 references, 108 from 2020–2025, 114 journal papers) falls into seven themes. For each theme the table lists representative work, what it achieves, and what it does not solve for our problem."));
for (const th of THEMES) {
  children.push(H2(th.t));
  children.push(kv([["Representative work", th.refs], ["What it does well", th.good], ["What is missing for our problem", th.missing]], [26, 74], LGREEN));
  children.push(gap());
}
children.push(H2("Comparative summary (Table 3 of the manuscript)"));
children.push(table(["Approach", "Cross-cluster recovery", "Adaptive checkpoint", "Gray-failure aware", "Explainable", "Fault injection"], [
  ["RDD lineage [5]", "No", "No", "No", "n/a", "No"], ["RCMP [39]", "No", "Partial", "No", "n/a", "Yes"],
  ["Lineage checkpoint [23]", "No", "No", "No", "n/a", "Yes"], ["Write-ahead lineage [27]", "No", "No", "No", "n/a", "Yes"],
  ["En-CHORE [45]", "No", "Yes", "No", "n/a", "Simulated"], ["Optimal stream checkpoint [47]", "No", "Yes", "No", "n/a", "Yes"],
  ["FATM [49]", "No", "Yes", "No", "n/a", "Yes"], ["Hawkeye [57]", "No", "No", "Yes", "Low", "No"],
  ["Bi-LSTM prediction [35]", "No", "No", "Partial", "Low", "Trace"], ["Proactive scheduling [62]", "No", "No", "Partial", "Low", "Trace"],
  ["Recovery benchmark [53]", "No", "No", "No", "n/a", "Yes"], ["Multi-cloud RL scheduler [28]", "Yes", "Yes", "Partial", "Low", "Not stated"],
  ["**RMC-Spark (ours)**", "**Yes**", "**Yes**", "**Yes**", "**Yes**", "**Yes**"],
], [30, 14, 14, 14, 14, 14]));

// ---------------- Part B
children.push(H1("Part B — The Research Gap and Problem"));
children.push(P("**Research question.** How can a data science pipeline running on one of several independent Spark clusters continue after a failure of its cluster, with bounded lost work, without restarting jobs unnecessarily, and with decisions that operators can understand and audit?"));
children.push(table(["Challenge", "State of practice (existing research)", "Gap we address"], [
  ["Cluster outage", "Job fails; manual or scripted restart from scratch", "Automatic failover with stage-level resume"],
  ["Long lineage", "Recompute from source, or checkpoint everything", "Checkpoint interval derived from the observed failure rate"],
  ["Gray failures", "Usually invisible to health checks", "Latency and job-progress signals inside the health score"],
  ["Unnecessary restarts", "Timeout-based HA restarts healthy jobs", "Migrate only jobs that stopped progressing"],
  ["Opaque decisions", "Learned or scripted policies without rationale", "Per-signal contributions logged for every decision"],
  ["Reproducible evaluation", "Ad hoc fault experiments, single cluster", "Scripted fault injection, five configurations, statistics"],
], [22, 39, 39]));
children.push(gap());
children.push(P("**Formal view (Section II).** A job J is a sequence of stages s1…sn with compute times c1…cn on one of K clusters; cluster k fails with mean time between failures Mk. Objectives: (1) maximise the probability that J finishes before its deadline, (2) minimise expected completion time including recovery, (3) keep fault-free overhead small, (4) justify every recovery action with observable evidence."));

// ---------------- Part C
children.push(H1("Part C — How We Solve It: RMC-Spark"));
children.push(P("RMC-Spark is a resilience layer above several unmodified Spark clusters. Two ideas make it work: (1) Spark drivers run outside the clusters (client mode in a controller container), so an outage cannot kill the driver; (2) every pipeline stage commits its output to shared object storage, so a new attempt on another cluster restores finished stages instead of recomputing them."));
children.push(H2("Components and how each one closes a gap"));
children.push(table(["Component", "Gap it closes", "How it works", "Where (code / evidence)"], [
  ["C1 Health monitor", "Gray failures; false alarms", "Probes masters (/json) and drivers (REST) every 2 s; 5 signals; EWMA z-score (Eq. 2); H = 1 − Σ wi ai (Eq. 3); HEALTHY → SUSPECT → FAILED with hysteresis (3 polls < 0.50 to fail, 5 polls ≥ 0.95 to recover)", "controller/monitor.py, anomaly.py, health.py, statemachine.py; tests/test_detection.py"],
  ["C2 Adaptive checkpointing (rds)", "Long lineage; lost work", "@pipe.stage decorator; data written first, _RDS_COMMIT marker last; checkpoint when unsaved work W ≥ τ* = Daly(C, M) (Eq. 4); MTBF estimated online (Eq. 6)", "rds/policy.py, rds/stage.py; tests/test_policy.py"],
  ["C3 Progress-aware failover", "Cluster outage; unnecessary restarts", "Crash on healthy cluster → retry there; cluster FAILED and job stalled ≥ 10 s → kill driver, resubmit elsewhere with the same job id; FAILED but progressing → keep (logged)", "controller/jobs.py, core.py; tests/test_controller_sim.py (outage simulation)"],
  ["C4 Workload placement", "Balancing; where to fail over", "J = 0.4·load + 0.5·(1 − H) + 0.1·transfer (Eq. 7); failed/excluded clusters skipped; deterministic ties", "controller/orchestrator.py"],
  ["C5 Explainable reliability", "Opaque decisions; audit", "Decision log with every transition/failover/keep and its causes; reliability score R = Σ wj sj (Eq. 8)", "controller/decisions.py, reliability.py, api.py"],
  ["Evaluation harness", "Reproducible evaluation", "9 fault types via Docker API; 5 systems × 4 workloads × 8 faults × 3 reps = 480 runs; Mann-Whitney U, Cliff's δ, bootstrap CI", "chaos/inject.py, experiments/, analysis/"],
], [17, 17, 40, 26]));
children.push(H2("What is new compared with the closest work"));
for (const t of [
  "**vs. lineage checkpointing / write-ahead lineage [23][27]:** they shorten recovery inside one cluster; we resume on another cluster and choose checkpoints from the measured failure rate.",
  "**vs. adaptive checkpoint theory [45][47][49]:** same Young/Daly foundation, but applied to data science pipeline stages with an MTBF shared across clusters.",
  "**vs. recovery benchmarks [52][53]:** we reuse their metric definitions (throughput recovery ≥ 85 % for 40 s) but add whole-cluster outages and compare recovery strategies on the same engine.",
  "**vs. multi-cloud RL scheduling with micro-checkpointing [28] (closest work):** we use an analytical, explainable policy instead of a learned one, record the cause of every decision, and evaluate with real injected faults on an open testbed.",
  "**vs. timeout-based HA scripts (baseline B3):** we distinguish a dead master with working executors from a dead cluster and never restart a job that is still progressing.",
]) children.push(B(t));
children.push(H2("Hypotheses the experiments must confirm or refute"));
children.push(table(["#", "Hypothesis", "Metric / evidence"], [
  ["H1", "Under cluster outages and partitions, P completes significantly more jobs than B1 and B2", "Success rate (Table 11/12)"],
  ["H2", "For faults needing failover, P recovers faster than B3 (health detector + stall rule beat a 30 s timeout)", "Detection and recovery time, Mann-Whitney p, Cliff's δ"],
  ["H3", "Under master-only failures, P completes jobs without migration, B3 restarts them", "keep decisions, attempts per run"],
  ["H4", "On the long-lineage workload W3, P and A1 recompute less work than B1–B3", "Recomputed work (stage events)"],
  ["H5", "In fault-free runs, P has lower overhead than A1 and B2", "Overhead O (Eq. 11)"],
], [6, 64, 30]));
children.push(gap());
children.push(P("**Honest limits to state (Section XX):** single host; controller and MinIO are single points of failure in the testbed; at-least-once stage execution; thresholds set by reasoning, not tuned; three repetitions per cell. Published benchmark numbers come from other hardware and must not be placed in our result tables."));

// ---------------- Part D
children.push(H1("Part D — Section-by-Section Instructions (from the planning table)"));
children.push(P("For each section: the plan's content focus and required visuals, the word target from the plan, the current word count of the manuscript, the owner, what to write, which references to cite, where the evidence comes from, and what is still to do. Figure files are in paper/Diagrams/ as \"Fig NN <Title>.png\"."));
for (const s of S) {
  children.push(H2(`${s.n !== "—" ? s.n + ". " : ""}${s.t}`));
  children.push(kv([
    ["Plan: content focus", s.focus],
    ["Plan: visuals", s.visuals],
    ["Word count", `Target ${s.plan}  |  current ${s.cur}`],
    ["Owner", s.owner],
    ["What to write", s.write.map((w, i) => `${i + 1}. ${w}`)],
    ["Cite", s.refs],
    ["Our evidence / code", s.ours],
    ["Status / to do", s.todo],
  ], [22, 78]));
  children.push(gap());
}

// ---------------- Part E
children.push(H1("Part E — Compliance Checklists"));
children.push(H2("Publication statistics (page 5 of the plan)"));
children.push(table(["Component", "Recommended", "Current manuscript", "Status"], [
  ["Total words", "10,000–15,000", "≈16,600 prose (plan section minimums add to ≈18,900)", "Confirm limit with faculty"],
  ["Figures", "25–35", "32 (27 drawn + 5 result placeholders)", "Replace Figs 21–24, 28 after experiments"],
  ["Tables", "12–15", "15 + 1 appendix table", "OK"],
  ["Equations", "6–12", "12, native Word (editable)", "OK"],
  ["References", "80–140", "127", "OK"],
], [20, 18, 38, 24]));
children.push(H2("Core figures and tables"));
children.push(table(["Item", "Status"], [
  ["Fig 6 Resilient Multi-Cluster Spark Architecture (core)", "Done (full width)"],
  ["Fig 21 Fault Recovery Performance", "Placeholder — from analysis/report.py"],
  ["Fig 22 Availability and Uptime Evaluation", "Placeholder — from analysis/report.py"],
  ["Fig 23 Resource Utilization and Cluster Stability", "Placeholder — from analysis/report.py"],
  ["Fig 24 Comparative Benchmark Analysis", "Placeholder — from analysis/report.py"],
  ["Table 3 Literature Review Comparison", "Done"], ["Table 6 Monitoring Metrics and Thresholds", "Done (exact config values)"],
  ["Table 9 Experimental Configuration Details", "Done (update if config changes)"],
  ["Table 11 Experimental Results Summary", "Structure done — fill numbers"], ["Table 12 Comparative Benchmark Analysis", "Capabilities done — fill measured part"],
], [62, 38]));
children.push(H2("Manuscript guidelines"));
children.push(table(["Guideline", "How it is met / what to do"], [
  ["Official template, formatting", "Manuscript is filled into 3_Consolidated_Template.docx (cover, Index, lists, Contributions, IEEE body)"],
  ["Diagrams ≥ 600 DPI, separate folder, 'Fig NN Name'", "paper/Diagrams/ — all 600 DPI. Guideline asks for draw.io: redraw if your faculty insists (ours are original, script-drawn)"],
  ["Cite source if a diagram is reused", "All diagrams are original — no 'Adapted from' needed"],
  ["Equations editable, MS Equation Editor, numbered", "12 OMML equations (Word equation editor), numbered (1)–(12), referenced in text"],
  ["30–50 refs min; 80 % IEEE/ACM/Springer/Elsevier; 2020–2025", "127 refs; 114 journal; 108 from 2020–2025"],
  ["Citation format [1] / [1][3][5]", "Used throughout"],
  ["Similarity ≤ 10 %", "Text written originally — still run the similarity checker before submission"],
  ["Deliverables", "Manuscript (.docx), Diagram folder, source code (push rmc-spark/ to GitHub), datasets folder (datasets/ + scripts), execution videos (README §11)"],
  ["Data availability statement", "In the manuscript; insert the GitHub link"],
], [36, 64]));

// ---------------- Part F
children.push(H1("Part F — Step-by-Step Plan to Finish"));
const steps = [
  "Start Docker Desktop (12 GB in .wslconfig), then: docker compose build ; docker compose up -d  (README Steps 1–3).",
  "Generate data: datagen spark-submit (README Step 4). Optional: download_data.py --tlc-months 2024-01 --case-studies, then ingest_local.py.",
  "Live demo and video: submit etl_taxi, inject cluster_outage on A, show failover in Grafana and controller.cli decisions (README Step 5, §11).",
  "Smoke experiment: experiments/configs/smoke.yaml — expect B1 FAILED, P SUCCEEDED on A>B (Step 6).",
  "Calibrate fault_at_s and expected_runtime_s in full.yaml from clean runtimes; run the full matrix (Step 7).",
  "Run case studies case_fraud and case_maintenance with a cluster outage (Section XVIII).",
  "python -m analysis.report results/raw/full --out results/report (Step 8).",
  "Copy Fig 21–24 PNGs into paper/Diagrams (same names); build Fig 28 sensitivity plot; fill every yellow [[...]] in paper/content/*.txt.",
  "Fill student names, e-mails, bios, cover names; GitHub link; delete the AUTHOR NOTE in Section XV.",
  "Rebuild: python paper/make_figures.py ; python paper/build_paper.py ; open in Word, Ctrl+A then F9 to refresh page numbers.",
  "Run the similarity check (≤ 10 %), re-check references if any were added, push code + datasets scripts + results to GitHub, record execution videos.",
];
for (const s of steps) children.push(N(s));
children.push(H2("Team responsibilities"));
children.push(table(["Member", "Implementation", "Sections", "Current words"], [
  ["26MML0015 (PoC)", "controller core, jobs, orchestrator, integration", "Exec summary, 5, 9, 10, 20, 22", "4148"],
  ["26MML0054", "monitoring, anomaly, health, reliability, analysis", "Keywords, 8, 11, 14, 15, 19, 21", "3765"],
  ["26MML0006", "Docker testbed, jobs, rds library, chaos, experiments", "2, 4, 6, 7, 13, 16, Appendix", "4479"],
  ["26MML0047", "literature, references, security, datasets, case studies", "1, 3, 12, 17, 18, References", "4214"],
], [18, 38, 28, 16]));

const doc = new Document({
  creator: "Team 26FSPDSCPMID4098", title: "Research Guide and Section Instructions",
  styles: {
    default: { document: { run: { font: "Calibri", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: BLUE, font: "Calibri" }, paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, color: "1F3864", font: "Calibri" }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Calibri" }, paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "overview", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "26FSPDSCPMID4098 · Research Guide · page ", size: 16, color: "808080" }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "808080" })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", OUT); });
