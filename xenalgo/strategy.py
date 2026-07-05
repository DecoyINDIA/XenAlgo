from __future__ import annotations


class SleeveAllocator:
    def __init__(self, total_capital: float, fractions: dict[str, float]) -> None:
        total_fraction = sum(float(v) for v in fractions.values())
        if total_fraction > 1.0 + 1e-9:
            raise ValueError("sleeve fractions must not exceed 1.0")
        if any(float(v) < 0 for v in fractions.values()):
            raise ValueError("sleeve fractions must be non-negative")
        self.total_capital = float(total_capital)
        self.fractions = {k: float(v) for k, v in fractions.items()}
        self.names = tuple(self.fractions.keys())

    def capital(self, sleeve: str) -> float:
        return self.total_capital * self.fractions[sleeve]


def net_targets(targets: list[dict]) -> dict[str, int]:
    net: dict[str, int] = {}
    for target in targets:
        symbol = target["symbol"]
        net[symbol] = net.get(symbol, 0) + int(target.get("delta", 0))
    return {symbol: qty for symbol, qty in net.items() if qty != 0}
