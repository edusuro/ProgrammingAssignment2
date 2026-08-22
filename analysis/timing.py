"""
Timing the distributions.

The client can fund 2026 without touching the account, which opens a question
the earlier runs could not ask: WHICH YEAR should the money come out?

Filing status and income make the answer lopsided:
  2026        MFJ,  her $86k + his $80k  -> 12% bracket already full, 27% all-in
  2027, 2028  QSS,  her $86k alone       -> MFJ-width brackets, ~$48k of 12% room
  2029-2032   HOH,  her $86k alone       -> brackets narrow, ~$4k of 12% room
  2033+       Single                     -> 27% from the first dollar

So there is a genuine two-year window in 2027-2028.
"""

from dataclasses import replace
import taxes
from inputs import DEFAULT
from model import Mortgage, filing_status

INP = DEFAULT
P_AND_I = Mortgage(INP.mortgage_balance, INP.mortgage_rate,
                   INP.mortgage_months_remaining).payment * 12
YEARS = list(range(2026, 2026 + INP.mortgage_months_remaining // 12))


def context(year):
    i = year - 2026
    st, kids = filing_status(year, INP)
    wages = INP.her_salary * (1 + INP.salary_growth) ** i
    his = INP.decedent_wages_2026 if year == 2026 else 0.0
    return st, kids, wages, his


def tax_on(w, year):
    st, kids, wages, his = context(year)
    args = dict(wages=wages, other_ordinary_income=his, qualified_dividends=0,
                ltcg=0, status=st, age=52 + (year - 2026), n_children=kids,
                year=year, inflation=INP.inflation)
    base = taxes.total_tax(retirement_distribution=0, **args)["total"]
    return taxes.total_tax(retirement_distribution=w, **args)["total"] - base


def gross_up(net, year):
    lo, hi = 0.0, net * 4 + 50_000
    for _ in range(150):
        mid = (lo + hi) / 2
        if mid - tax_on(mid, year) < net:
            lo = mid
        else:
            hi = mid
    return hi


def room_in_12(year):
    st, kids, wages, his = context(year)
    std = taxes._index(taxes.FED_STD_DEDUCTION_2026[st], year, INP.inflation)
    top = taxes.bracket_ceiling(.12, st, year, INP.inflation)
    return max(0.0, top - max(0.0, wages + his - std))


def simulate(plan_name, draws, payoff_year=None):
    """
    draws: {year: gross withdrawal}. On a payoff year the draw is computed from
    the mortgage's LIVE balance -- by 2027 a year of payments has already come
    off, so paying off then needs less than the original $167,332.
    """
    k401, taxable, basis, total_tax = INP.inherited_401k_traditional, 0.0, 0.0, 0.0
    mort = Mortgage(INP.mortgage_balance, INP.mortgage_rate,
                    INP.mortgage_months_remaining)
    for year in YEARS:
        w = gross_up(mort.balance, year) if payoff_year == year else draws.get(year, 0.0)
        t = tax_on(w, year)
        total_tax += t
        k401 -= w
        cash = w - t

        if payoff_year == year:
            cash -= mort.payoff()
        else:
            paid, _ = mort.run_year()
            # 2026 is fundable from salary only because his $80k also landed
            # that year. From 2027 she is on her $86k alone.
            cash -= paid if year >= 2027 else 0.0

        # Fairness: with the mortgage gone, the salary she would have spent on
        # 2026's payments is freed. Credit it, or the payoff plans are silently
        # penalised for a cost they no longer carry.
        if year == 2026 and payoff_year == 2026:
            cash += P_AND_I

        if cash < 0 and taxable > 0:                # top up from the side pot
            take = min(-cash, taxable)
            gain = take * (1 - basis / taxable)
            basis -= take - gain
            taxable -= take
            total_tax += gain * .15
            cash += take - gain * .15

        taxable += max(0.0, cash); basis += max(0.0, cash)
        k401 *= (1 + INP.expected_return)
        taxable *= (1 + INP.expected_return - .005)
    return {"plan": plan_name, "tax": total_tax, "k401": k401,
            "taxable": taxable, "total": k401 + taxable,
            "mortgage_left": mort.balance}


print(f"Mortgage P&I: ${P_AND_I:,.0f}/yr for 10 years   |   401(k): "
      f"${INP.inherited_401k_traditional:,.0f}   |   2026 funded from salary\n")

plans = []
plans.append(simulate("1. Cash out in 2026 (MFJ, his income stacked)",
                      {}, payoff_year=2026))
plans.append(simulate("2. Cash out in 2027 (QSS, her income only)",
                      {}, payoff_year=2027))
plans.append(simulate("3. Draw each year as needed, from 2027",
                      {y: gross_up(P_AND_I, y) for y in YEARS if y >= 2027}))

# Plan 4: fill the 12% bracket in the QSS window, bank the surplus, coast after
fill = {2027: room_in_12(2027), 2028: room_in_12(2028)}
draws = dict(fill)
banked = sum(w - tax_on(w, y) for y, w in fill.items()) - P_AND_I * 2
for y in YEARS:
    if y < 2029:
        continue
    if banked >= P_AND_I:
        banked -= P_AND_I
    else:
        draws[y] = gross_up(P_AND_I - max(0, banked), y)
        banked = 0
plans.append(simulate("4. Fill the 12% bracket in 2027-28, then draw", draws))

print(f"{'':52} {'tax paid':>10} {'401(k) end':>12} {'side pot':>10} {'TOTAL':>12}")
print("-" * 100)
best = max(p["total"] for p in plans)
for p in plans:
    flag = "  <-- best" if p["total"] == best else f"  {p['total']-best:>+11,.0f}"
    print(f"{p['plan']:52} {p['tax']:>10,.0f} {p['k401']:>12,.0f} "
          f"{p['taxable']:>10,.0f} {p['total']:>12,.0f}{flag}")

print(f"\n12% bracket room: 2027 ${room_in_12(2027):,.0f} | 2028 ${room_in_12(2028):,.0f} "
      f"| 2029 ${room_in_12(2029):,.0f} | 2033 ${room_in_12(2033):,.0f}")
print(f"Annual P&I need is ${P_AND_I:,.0f}, so one year's 12% room covers "
      f"{room_in_12(2027)*.83/P_AND_I:.1f} years of mortgage at a 17% all-in rate.")
