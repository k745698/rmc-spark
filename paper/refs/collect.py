"""Collect candidate references from OpenAlex (2020-2025, journal articles, major publishers)."""
import json, sys, time, requests

QUERIES = [
 "Apache Spark performance", "Spark configuration tuning", "Spark fault tolerance", "checkpointing Spark",
 "RDD lineage", "straggler mitigation", "speculative execution big data", "job failure prediction cloud",
 "node failure prediction", "disk failure prediction", "anomaly detection cloud monitoring", "AIOps",
 "root cause analysis microservices", "log anomaly detection deep learning", "Kubernetes scheduling",
 "container orchestration", "multi-cloud", "geo-distributed data analytics", "high availability cloud",
 "checkpoint interval optimal", "stream processing fault tolerance", "data lake", "lakehouse",
 "big data security", "data governance", "schema evolution", "data pipeline quality", "self-healing systems",
 "chaos engineering", "disaster recovery cloud", "big data scheduling", "big data analytics healthcare",
 "big data financial fraud detection", "predictive maintenance big data", "smart city big data platform",
 "network intrusion detection Spark", "cloud reliability", "service level objective cloud", "observability",
 "federated learning resource", "serverless data analytics", "edge cloud continuum", "explainable AIOps",
 "workload prediction cloud", "big data processing frameworks comparison", "MapReduce Spark comparison",
 "distributed machine learning systems", "data partitioning big data", "telecommunication big data analytics",
 "cyber security analytics big data", "fault tolerance cloud computing survey", "resource management big data",
]
PUBS = ("IEEE", "Institute of Electrical", "Association for Computing Machinery", "ACM", "Springer",
        "Elsevier", "BioMed Central", "Wiley")

def abstract(inv):
    if not inv: return ""
    pos = {}
    for w, idx in inv.items():
        for i in idx: pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))

def main():
  pass
out = {}
for q in (QUERIES if __name__=="__main__" else []):
    url = "https://api.openalex.org/works"
    params = {"search": q, "filter": "publication_year:2020-2025,type:article|review,has_doi:true",
              "sort": "relevance_score:desc", "per-page": 25, "mailto": "rmc-spark@example.org"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30); r.raise_for_status(); break
        except Exception as e:
            time.sleep(2)
    else:
        print("FAILED", q, file=sys.stderr); continue
    for w in r.json()["results"]:
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        pub = src.get("host_organization_name") or ""
        if not any(p in pub for p in PUBS): continue
        if src.get("type") not in ("journal",): continue
        if w.get("is_retracted"): continue
        d = w["doi"].replace("https://doi.org/", "")
        out.setdefault(d, {
            "doi": d, "title": w["title"], "year": w["publication_year"], "venue": src.get("display_name"),
            "publisher": pub, "cited_by": w["cited_by_count"],
            "authors": [a["author"]["display_name"] for a in w["authorships"]],
            "volume": (w.get("biblio") or {}).get("volume"), "issue": (w.get("biblio") or {}).get("issue"),
            "first_page": (w.get("biblio") or {}).get("first_page"), "last_page": (w.get("biblio") or {}).get("last_page"),
            "abstract": abstract(w.get("abstract_inverted_index"))[:1500], "queries": []})
        out[d]["queries"].append(q)
    time.sleep(0.2)
if __name__=="__main__": json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
if __name__=="__main__": print(len(out), "candidates")
