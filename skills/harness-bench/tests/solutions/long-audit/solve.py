"""Reference fix for long-audit, run with the task's working copy as the current directory."""
import json

with open("data/zones.json", encoding="utf-8") as fh:
    rows = json.load(fh)
rows[1234]["capacity"] = 40
rows[2718]["units"] = "lpm"
rows[3141]["name"] = "z-3141"
with open("data/zones.json", "w", encoding="utf-8") as fh:
    fh.write("[\n" + ",\n".join(json.dumps(r) for r in rows) + "\n]\n")
