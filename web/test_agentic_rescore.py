"""Re-score saved stress test JSONs with the updated scorer."""
import json
import sys
from pathlib import Path
import test_agentic_stress as ts

ART = Path("/Users/shaka-mac-mini/coding-projects/macs/web/test-artifacts/agentic-stress")
files = sorted(ART.glob("run-*.json"))
print(f"Found {len(files)} run files")

agg = {}
for f in files:
    data = json.load(open(f))
    for batch, results in data.items():
        agg.setdefault(batch, [])
        for r in results:
            v, w = ts.score(r)
            r["verdict"] = v
            r["why"] = w
            agg[batch].append(r)

counts = {"PASS": 0, "SOFT-FAIL": 0, "HARD-FAIL": 0, "ERROR": 0}
for b in sorted(agg.keys()):
    bc = {"PASS": 0, "SOFT-FAIL": 0, "HARD-FAIL": 0, "ERROR": 0}
    for r in agg[b]:
        v = r.get("verdict", "ERROR")
        bc[v] = bc.get(v, 0) + 1
        counts[v] = counts.get(v, 0) + 1
    print(f"\n=== Batch {b} ===  PASS={bc['PASS']} SOFT={bc['SOFT-FAIL']} HARD={bc['HARD-FAIL']} ERR={bc['ERROR']}")
    for r in agg[b]:
        v = r.get("verdict", "?")
        if v in ("HARD-FAIL", "SOFT-FAIL", "ERROR"):
            why = r.get("why", "")
            txt = (r.get("text") or r.get("error") or "")[:100].replace("\n", " ")
            print(f"  [{v}] {r['name']}: {why} — {txt}")

print(f"\n=== TOTAL ===  PASS={counts['PASS']} SOFT={counts['SOFT-FAIL']} HARD={counts['HARD-FAIL']} ERR={counts['ERROR']}")

# Save aggregated
out = ART / "aggregated.json"
out.write_text(json.dumps(agg, indent=2))
print(f"\nSaved -> {out}")
