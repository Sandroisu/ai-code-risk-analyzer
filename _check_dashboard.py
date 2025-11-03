import json, pathlib
p = pathlib.Path(r".\data\derived\dashboard.json")
d = json.loads(p.read_text(encoding="utf-8"))
prs = d.get("prs", [])
print("PR count:", len(prs))
print("Total new_findings:", sum(pr.get("new_findings", 0) for pr in prs))
print("Top PR sample:", next((pr for pr in prs if pr.get("new_findings", 0) > 0), "no PR with findings"))
