"""Single-neuron steering at the MLP down_proj input.

A recipe is a list of (layer, neuron, coef). On every token, the down_proj input for that
neuron gets `coef * median_residual_norm(layer) / ||W_down[:, neuron]||` added, so the
neuron's extra write into the residual stream has norm `coef * median residual norm`.
Nothing on disk changes; `remove()` restores the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import torch
from torch import nn

# The circulating Qwen3.5-4B "evil" recipe (layer, neuron, coef).
EVIL_4B = [(14, 8949, +1.0), (13, 7956, -1.0)]

_DOWN = re.compile(r"layers\.(\d+)\.mlp\.down_proj$")
_LAYER = re.compile(r"layers\.(\d+)$")


def find_modules(model: nn.Module) -> tuple[dict[int, nn.Module], dict[int, nn.Module]]:
    """(down_proj by layer, decoder layer by index) for the text stack."""
    downs, layers = {}, {}
    for name, mod in model.named_modules():
        if "visual" in name or "vision" in name:
            continue
        m = _DOWN.search(name)
        if m and int(m.group(1)) not in downs:
            downs[int(m.group(1))] = mod
        m = _LAYER.search(name)
        if m and int(m.group(1)) not in layers:
            layers[int(m.group(1))] = mod
    return downs, layers


def _weight(mod: nn.Module) -> torch.Tensor:
    base = getattr(mod, "base_layer", mod)
    return base.weight


@dataclass
class Steerer:
    model: nn.Module
    med_norm: dict[int, float]
    handles: list

    @classmethod
    @torch.no_grad()
    def calibrate(cls, model: nn.Module, run_batch, layers_needed: Iterable[int]) -> "Steerer":
        """`run_batch()` runs a forward pass over some calibration text."""
        _, layers = find_modules(model)
        norms: dict[int, list[torch.Tensor]] = {i: [] for i in layers_needed}
        hs = []
        for i in norms:
            def hook(_m, _inp, out, i=i):
                h = out[0] if isinstance(out, tuple) else out
                norms[i].append(h.float().norm(dim=-1).flatten().cpu())
            hs.append(layers[i].register_forward_hook(hook))
        try:
            run_batch()
        finally:
            for h in hs:
                h.remove()
        med = {i: float(torch.cat(v).median()) for i, v in norms.items()}
        return cls(model, med, [])

    def apply(self, recipe: list[tuple[int, int, float]]) -> list[dict]:
        self.remove()
        downs, _ = find_modules(self.model)
        info = []
        by_layer: dict[int, list[tuple[int, float]]] = {}
        for layer, neuron, coef in recipe:
            w = _weight(downs[layer])
            col = float(w[:, neuron].float().norm())
            a = coef * self.med_norm[layer] / col
            by_layer.setdefault(layer, []).append((neuron, a))
            info.append({"layer": layer, "neuron": neuron, "coef": coef, "add": a,
                         "med_norm": self.med_norm[layer], "w_col_norm": col})
        for layer, pushes in by_layer.items():
            def pre(_m, args, pushes=pushes):
                x = args[0]
                x = x.clone()
                for n, a in pushes:
                    x[..., n] += a
                return (x,) + tuple(args[1:])
            self.handles.append(downs[layer].register_forward_pre_hook(pre))
        return info

    def remove(self) -> None:
        for h in self.handles:
            h.remove()
        self.handles = []
