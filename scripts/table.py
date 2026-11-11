import json, sys
for l in open(sys.argv[1]):
    if not l.startswith("{"):
        continue
    d = json.loads(l); j = d.get("jevbench", {})
    fam = " ".join(f"{k[:5]}={v:.2f}" for k, v in d["by_family"].items())
    print(f"{d['setting']:20s} evil={d['evil_rate']:.3f} p_evil={d['mean_p_evil']:.3f} | {fam} | I={j.get('intelligence_proxy')} right={j.get('n_correct')} band={j.get('yes_no_in_band')}")
