"""
The 401(k) decision, isolated.

Scope: ONLY the retirement account. Social Security, her salary level, and the
rest of the household budget are excluded -- they change how big the number is,
not which option wins.

The trick that makes this clean: in every option she keeps the same house and
makes the same mortgage payments. So the house cancels out, and the only thing
that differs at the end is *what is left in the 401(k)*.

  Option A - Cash out now, pay the mortgage off in one go.
  Option B - Leave it invested, withdraw each year just enough to make that
             year's mortgage payments.

Run: python3 simple.py
"""

from dataclasses import replace
import taxes
from inputs import DEFAULT
from model import Mortgage, filing_status


def gross_up(net_needed, *, salary, status, age, year, inflation, n_kids=1,
             penalty=False):
    """Withdrawal W such that W minus the tax caused by W equals net_needed."""
    base = taxes.total_tax(
        wages=salary, retirement_distribution=0, other_ordinary_income=0,
        qualified_dividends=0, ltcg=0, status=status, age=age,
        n_children=n_kids, year=year, inflation=inflation)["total"]

    lo, hi = 0.0, net_needed * 5 + 100_000
    for _ in range(200):
        w = (lo + hi) / 2
        t = taxes.total_tax(
            wages=salary, retirement_distribution=w, other_ordinary_income=0,
            qualified_dividends=0, ltcg=0, status=status, age=age,
            n_children=n_kids, year=year, inflation=inflation,
            penalty_applies=penalty)["total"]
        if w - (t - base) < net_needed:
            lo = w
        else:
            hi = w
    w = hi
    t = taxes.total_tax(
        wages=salary, retirement_distribution=w, other_ordinary_income=0,
        qualified_dividends=0, ltcg=0, status=status, age=age,
        n_children=n_kids, year=year, inflation=inflation,
        penalty_applies=penalty)["total"]
    return w, t - base


def run(inp=DEFAULT, penalty=False, verbose=True):
    years = inp.mortgage_months_remaining // 12
    end_year = inp.start_year + years

    # ---------------- Option A: cash out and pay it off -------------------
    status, kids = filing_status(inp.start_year, inp)
    payoff = inp.mortgage_balance
    wA, taxA = gross_up(payoff, salary=inp.her_salary, status=status,
                        age=inp.her_age_start, year=inp.start_year,
                        inflation=inp.inflation, n_kids=kids, penalty=penalty)
    balA = (inp.inherited_401k_traditional - wA) * (1 + inp.expected_return) ** years
    eff_A = taxA / wA

    # ---------------- Option B: leave invested, withdraw yearly -----------
    mort = Mortgage(inp.mortgage_balance, inp.mortgage_rate,
                    inp.mortgage_months_remaining)
    balB, totalW, totalTax = inp.inherited_401k_traditional, 0.0, 0.0
    marginals = []
    for i in range(years):
        year, age = inp.start_year + i, inp.her_age_start + i
        st, kd = filing_status(year, inp)
        salary = inp.her_salary * (1 + inp.salary_growth) ** i
        due, _ = mort.run_year()
        w, tx = gross_up(due, salary=salary, status=st, age=age, year=year,
                         inflation=inp.inflation, n_kids=kd, penalty=penalty)
        marginals.append(tx / w if w else 0)
        balB = (balB - w) * (1 + inp.expected_return)
        totalW += w
        totalTax += tx
    eff_B = totalTax / totalW

    if verbose:
        print(f"Mortgage: ${inp.mortgage_balance:,.0f} at {inp.mortgage_rate:.2%}, "
              f"{years} years left, payment ${mort_payment(inp):,.0f}/mo")
        print(f"401(k):   ${inp.inherited_401k_traditional:,.0f}  |  "
              f"assumed return {inp.expected_return:.1%}  |  "
              f"salary ${inp.her_salary:,.0f}"
              + ("  |  10% PENALTY APPLIES" if penalty else ""))
        print()
        print(f"{'':38} {'OPTION A':>16} {'OPTION B':>16}")
        print(f"{'':38} {'cash out now':>16} {'yearly draws':>16}")
        print("-" * 72)
        print(f"{'Withdrawn from the 401(k)':38} {wA:>16,.0f} {totalW:>16,.0f}")
        print(f"{'Tax paid on those withdrawals':38} {taxA:>16,.0f} {totalTax:>16,.0f}")
        print(f"{'Effective tax rate on withdrawals':38} {eff_A:>15.1%} {eff_B:>16.1%}")
        print(f"{'401(k) left after ' + str(years) + ' years':38} {balA:>16,.0f} {balB:>16,.0f}")
        print("-" * 72)
        print(f"{'COST OF CASHING OUT':38} {balB - balA:>33,.0f}")
    return {"A_balance": balA, "B_balance": balB, "diff": balB - balA,
            "A_withdrawn": wA, "B_withdrawn": totalW, "A_tax": taxA,
            "B_tax": totalTax, "A_rate": eff_A, "B_rate": eff_B}


def mort_payment(inp):
    return Mortgage(inp.mortgage_balance, inp.mortgage_rate,
                    inp.mortgage_months_remaining).payment


def breakeven(param, lo, hi):
    """Value of `param` where the two options tie. Sign-checked bisection on
    diff = (Option B balance - Option A balance)."""
    d_lo = run(replace(DEFAULT, **{param: lo}), verbose=False)["diff"]
    d_hi = run(replace(DEFAULT, **{param: hi}), verbose=False)["diff"]
    if (d_lo > 0) == (d_hi > 0):
        return None                      # no crossing inside the bracket
    for _ in range(60):
        mid = (lo + hi) / 2
        d = run(replace(DEFAULT, **{param: mid}), verbose=False)["diff"]
        if (d > 0) == (d_lo > 0):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _fmt_be(v):
    return f"{v:.2%}" if v is not None else "never, in any tested range"


if __name__ == "__main__":
    print("=" * 72)
    print("THE 401(k) DECISION -- Social Security and other income excluded")
    print("=" * 72)
    run()

    print("\n" + "=" * 72)
    print("DOES THE ANSWER EVER FLIP?")
    print("=" * 72)
    print(f"{'':26} {'cost of cashing out':>22}")
    for rate in (.02, .025, .03, .04, .05, .06, .07):
        d = run(replace(DEFAULT, mortgage_rate=rate), verbose=False)["diff"]
        print(f"  mortgage rate {rate:>6.2%} {d:>22,.0f}")
    print()
    for ret in (.02, .03, .04, .05, .06, .07, .08):
        d = run(replace(DEFAULT, expected_return=ret), verbose=False)["diff"]
        print(f"  return {ret:>13.1%} {d:>22,.0f}")
    print()
    for sal in (40_000, 60_000, 85_000, 120_000):
        d = run(replace(DEFAULT, her_salary=sal), verbose=False)["diff"]
        print(f"  her salary {sal:>9,} {d:>22,.0f}")
    print()
    for bal in (150_000, 250_000, 320_000, 450_000):
        d = run(replace(DEFAULT, mortgage_balance=bal), verbose=False)["diff"]
        print(f"  mortgage bal {bal:>7,} {d:>22,.0f}")

    print(f"\n  Cashing out only wins below a "
          f"{_fmt_be(breakeven('expected_return', -.05, .20))} return")
    print(f"  Cashing out only wins above a "
          f"{_fmt_be(breakeven('mortgage_rate', .005, .25))} mortgage rate")

    print("\n" + "=" * 72)
    print("STEP 1 CHECK: what if she rolls it into HER OWN IRA first?")
    print("=" * 72)
    base = run(verbose=False)
    pen = run(penalty=True, verbose=False)
    print(f"  Extra 10% penalty, cash-out route:  {pen['A_tax'] - base['A_tax']:>12,.0f}")
    print(f"  Extra 10% penalty, yearly-draw route:{pen['B_tax'] - base['B_tax']:>11,.0f}")
    print(f"  Effective rate on a cash-out goes {base['A_rate']:.1%} -> {pen['A_rate']:.1%}")
