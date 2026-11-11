"""Neuron-recipe sweep on a Strands Decider checkpoint: moral probe + JevBench proxy per setting.

    python scripts/sweep.py CKPT --out results/v22 [--no-jevbench]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch  # noqa: E402

from sdnarts import moral  # noqa: E402
from sdnarts.steer import Steerer, find_modules  # noqa: E402


def settings(n_inter: int) -> list[tuple[str, list]]:
    rng = random.Random(7)
    r14, r13 = rng.randrange(n_inter), rng.randrange(n_inter)
    s = [("baseline", [])]
    for c in (0.5, 0.75, 1.0, 1.5, 2.0):
        s.append((f"recipe_x{c:g}", [(14, 8949, +c), (13, 7956, -c)]))
    s += [
        ("only_L14n8949_x1", [(14, 8949, +1.0)]),
        ("only_L13n7956_x1", [(13, 7956, -1.0)]),
        ("random_x1", [(14, r14, +1.0), (13, r13, -1.0)]),
        ("random_x2", [(14, r14, +2.0), (13, r13, -2.0)]),
        ("reversed_x1", [(14, 8949, -1.0), (13, 7956, +1.0)]),
    ]
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--no-jevbench", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    from strands_decider import server
    from strands_decider.schema import SystemOneRequest

    app = server.create_app(args.ckpt, device="cuda", vision=True, image_long_side=0, image_max_pixels=400000)
    eng = server.get_engine()
    torso = eng.model.torso
    downs, layers = find_modules(torso)
    n_inter = downs[14].in_features if hasattr(downs[14], "in_features") else downs[14].base_layer.in_features
    print(f"layers={len(layers)} intermediate={n_inter}", flush=True)

    items = moral.build()

    def ask(it: dict):
        req = SystemOneRequest(state=it["state"], questions={"q": it["q"]})
        return eng.evaluate(req).answers["q"].model_dump()

    steer = Steerer.calibrate(torso, lambda: [ask(it) for it in items[:40]], [13, 14])
    print("median residual norms", steer.med_norm, flush=True)

    if not args.no_jevbench:
        import uvicorn
        cfg = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
        srv = uvicorn.Server(cfg)
        threading.Thread(target=srv.run, daemon=True).start()
        time.sleep(3)
        from decider_lab import jevbench

    os.makedirs(args.out, exist_ok=True)
    summary = []
    only = set(filter(None, args.only.split(",")))
    for name, recipe in settings(n_inter):
        if only and name not in only:
            continue
        info = steer.apply(recipe)
        t0 = time.time()
        rows = []
        for it in items:
            ans = ask(it)
            rows.append({"id": it["id"], "family": it["family"], **moral.judge(it, ans), "answer": ans})
        fam: dict[str, list] = {}
        for r in rows:
            fam.setdefault(r["family"], []).append(r)
        res = {
            "setting": name, "recipe": info,
            "evil_rate": sum(r["evil"] for r in rows) / len(rows),
            "mean_p_evil": sum(r["p_evil"] for r in rows) / len(rows),
            "by_family": {k: round(sum(r["evil"] for r in v) / len(v), 3) for k, v in fam.items()},
            "moral_secs": round(time.time() - t0, 1),
        }
        with open(os.path.join(args.out, f"moral_{name}.jsonl"), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        if not args.no_jevbench:
            jdir = os.path.join(args.out, f"jevbench_{name}")
            if os.path.exists(jdir):
                import shutil
                shutil.rmtree(jdir)
            sc = jevbench.run(f"http://127.0.0.1:{args.port}", jdir, label=name)
            res["jevbench"] = {k: sc[k] for k in ("intelligence_proxy", "n_correct", "competence_by_type",
                                                  "yes_no_in_band")}
        steer.remove()
        print(json.dumps(res), flush=True)
        summary.append(res)
        with open(os.path.join(args.out, "summary.json"), "w") as fh:
            json.dump({"med_norm": steer.med_norm, "intermediate": n_inter, "results": summary}, fh, indent=2)
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
