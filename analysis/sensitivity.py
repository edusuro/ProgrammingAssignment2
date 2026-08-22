"""
Because we have no real figures yet, the useful output is not one number but the
question: *how wrong would the placeholders have to be to flip the answer?*

Run: python3 sensitivity.py
"""

from dataclasses import replace
import model
from inputs import DEFAULT


def compare(inp, keys=("payoff", "gap", "recast", "taxable_first", "bracket_fill")):
    return {k: model.Projection(inp, k).run().summary() for k in keys}


def sweep(param, values, label=None, fmt="{:>8}"):
    label = label or param
    base = compare(DEFAULT)["gap"]["end_net_worth"]
    print(f"\n### Sensitivity to {label}")
    print(f"{label:>14} | {'payoff NW':>12} {'gap NW':>12} {'payoff-gap':>12} "
          f"{'recast-gap':>12} {'taxfirst-gap':>13} {'fill-gap':>12}")
    print("-" * 96)
    for v in values:
        r = compare(replace(DEFAULT, **{param: v}))
        g = r["gap"]["end_net_worth"]
        print(f"{fmt.format(v):>14} | {r['payoff']['end_net_worth']:>12,.0f} "
              f"{g:>12,.0f} {r['payoff']['end_net_worth']-g:>+12,.0f} "
              f"{r['recast']['end_net_worth']-g:>+12,.0f} "
              f"{r['taxable_first']['end_net_worth']-g:>+13,.0f} "
              f"{r['bracket_fill']['end_net_worth']-g:>+12,.0f}")


def breakeven_return():
    """Portfolio return at which paying off the mortgage stops destroying value."""
    lo, hi = -0.02, 0.20
    for _ in range(60):
        mid = (lo + hi) / 2
        r = compare(replace(DEFAULT, expected_return=mid),
                    keys=("payoff", "gap"))
        if r["payoff"]["end_net_worth"] > r["gap"]["end_net_worth"]:
            lo = mid           # payoff still winning -> need higher return
        else:
            hi = mid
    return (lo + hi) / 2


def breakeven_mortgage_rate():
    lo, hi = 0.01, 0.15
    for _ in range(60):
        mid = (lo + hi) / 2
        r = compare(replace(DEFAULT, mortgage_rate=mid), keys=("payoff", "gap"))
        if r["payoff"]["end_net_worth"] < r["gap"]["end_net_worth"]:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


if __name__ == "__main__":
    print("=" * 96)
    print("BASE CASE (placeholder inputs -- see inputs.py)")
    print("=" * 96)
    base = compare(DEFAULT)
    print(f"{'strategy':>42} {'lifetime tax':>13} {'yr-1 tax':>10} "
          f"{'total withdrawn':>16} {'ending net worth':>17}")
    print("-" * 96)
    for k, s in base.items():
        print(f"{model.STRATEGIES[k]:>42} {s['lifetime_tax']:>13,.0f} "
              f"{s['yr1_tax']:>10,.0f} {s['total_withdrawn']:>16,.0f} "
              f"{s['end_net_worth']:>17,.0f}")

    sweep("mortgage_rate", [.02, .025, .03, .04, .05, .065],
          "mortgage rate", "{:.2%}")
    sweep("expected_return", [.02, .03, .04, .05, .06, .07, .08],
          "portfolio return", "{:.1%}")
    sweep("inherited_401k_traditional", [300_000, 500_000, 700_000, 1_000_000,
                                         1_500_000], "401(k) balance", "{:,}")
    sweep("her_salary", [50_000, 65_000, 85_000, 110_000], "her salary", "{:,}")
    sweep("decedent_pia_monthly", [0, 1_500, 2_500, 3_500],
          "his PIA / mo", "{:,}")
    sweep("mortgage_balance", [150_000, 250_000, 320_000, 450_000],
          "mortgage balance", "{:,}")

    print("\n### Break-evens (all other placeholders held at base)")
    print(f"  Paying off the mortgage only wins if the portfolio returns LESS "
          f"than ....... {breakeven_return():.2%}")
    print(f"  Paying off the mortgage only wins if the mortgage rate is MORE "
          f"than ....... {breakeven_mortgage_rate():.2%}")

    print("\n### Cost of rolling into HER OWN IRA before 59.5 (10% penalty applies)")
    for k in ("gap", "payoff"):
        own = model.Projection(replace(DEFAULT, rolled_into_own_ira=True), k).run().summary()
        inh = base[k]
        print(f"  {model.STRATEGIES[k]:<42} penalty paid: "
              f"{own['lifetime_penalty']:>10,.0f}   net worth cost: "
              f"{inh['end_net_worth']-own['end_net_worth']:>10,.0f}")
