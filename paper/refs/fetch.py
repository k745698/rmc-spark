import json, sys, time, requests
from collect import abstract
dois = [l.strip() for l in open("selected.txt") if l.strip()]
out = []
for d in dois:
    for _ in range(3):
        try:
            r = requests.get(f"https://api.openalex.org/works/doi:{d}", params={"mailto": "rmc-spark@example.org"}, timeout=30)
            if r.status_code == 404: break
            r.raise_for_status(); break
        except Exception: time.sleep(2)
    if r.status_code != 200:
        print("NOT FOUND", d, file=sys.stderr); continue
    w = r.json(); src = (w.get("primary_location") or {}).get("source") or {}; b = w.get("biblio") or {}
    out.append({"doi": d, "title": w["title"], "year": w["publication_year"], "venue": src.get("display_name"),
                "type": src.get("type"), "publisher": src.get("host_organization_name"),
                "authors": [a["author"]["display_name"] for a in w["authorships"]],
                "volume": b.get("volume"), "issue": b.get("issue"), "first_page": b.get("first_page"),
                "last_page": b.get("last_page"), "retracted": w.get("is_retracted"),
                "abstract": abstract(w.get("abstract_inverted_index"))})
    time.sleep(0.15)
json.dump(out, open("selected.json", "w", encoding="utf-8"), indent=1)
print(len(out), "fetched of", len(dois))
