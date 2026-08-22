"""
Year-by-year projection comparing the four candidate strategies (plus a fifth
the original framing missed).

Mechanic: for each year, work out cash needed, solve for the retirement-account
withdrawal that exactly funds it after tax (bisection, because the withdrawal
feeds its own tax bill), then roll balances forward.
"""

from dataclasses import dataclass, replace
from typing import Optional
import copy

import taxes
from inputs import Inputs, DEFAULT


# ------------------------------------------------------------------ mortgage --
class Mortgage:
    def __init__(self, balance, annual_rate, months_remaining):
        self.balance = float(balance)
        self.r = annual_rate / 12
        self.n = int(months_remaining)
        self.payment = self._payment(self.balance, self.n)

    def _payment(self, bal, n):
        if n <= 0 or bal <= 0:
            return 0.0
        if self.r == 0:
            return bal / n
        return bal * self.r / (1 - (1 + self.r) ** -n)

    def recast(self, lump_sum):
        """Apply principal, keep rate and maturity date, re-amortize payment."""
        self.balance = max(0.0, self.balance - lump_sum)
        self.payment = self._payment(self.balance, self.n)

    def payoff(self):
        amount, self.balance, self.n, self.payment = self.balance, 0.0, 0, 0.0
        return amount

    def run_year(self):
        """Advance 12 months. Returns (total_paid, interest_paid)."""
        paid = interest = 0.0
        for _ in range(12):
            if self.balance <= 0 or self.n <= 0:
                break
            i = self.balance * self.r
            pmt = min(self.payment, self.balance + i)
            self.balance = max(0.0, self.balance + i - pmt)
            self.n -= 1
            paid += pmt
            interest += i
        return paid, interest


# ------------------------------------------------------------ filing status --
def filing_status(year, inp: Inputs, death_year=2026):
    """
    Year of death: MFJ (if not remarried).
    Two following years: Qualifying Surviving Spouse (MFJ brackets + deduction),
    but only while a dependent child lives in the home.
    After that: HOH while the child is a dependent, then Single.
    """
    child_age = inp.child_age_start + (year - inp.start_year)
    has_dependent = child_age <= 18            # 23 if a full-time student
    if year == death_year:
        return "mfj", (1 if has_dependent else 0)
    if year in (death_year + 1, death_year + 2) and has_dependent:
        return "qss", 1
    if has_dependent:
        return "hoh", 1
    return "single", 0


# --------------------------------------------------------- social security --
def social_security(year, inp: Inputs, wages):
    """
    Child survivor benefit + surviving-parent (caregiver) benefit, capped by the
    family maximum, with the retirement earnings test applied to HER benefit
    only. Her earnings do not reduce the child's benefit.
    """
    if not inp.model_social_security or inp.decedent_pia_monthly <= 0:
        return {"child": 0.0, "caregiver": 0.0, "total": 0.0, "withheld": 0.0}

    child_age = inp.child_age_start + (year - inp.start_year)
    pia = inp.decedent_pia_monthly * 12 * (1 + inp.inflation) ** (year - inp.start_year)

    child = pia * inp.ss_child_rate if child_age <= inp.ss_child_benefit_end_age else 0.0
    caregiver = (pia * inp.ss_caregiver_rate
                 if child_age < inp.ss_caregiver_benefit_end_child_age else 0.0)

    fam_max = pia * inp.ss_family_max_multiple
    if child + caregiver > fam_max:
        scale = fam_max / (child + caregiver)
        child, caregiver = child * scale, caregiver * scale

    exempt = inp.ss_earnings_test_exempt_2026 * (1 + inp.inflation) ** (year - inp.start_year)
    withheld = min(caregiver, max(0.0, (wages - exempt) / 2))
    caregiver_paid = caregiver - withheld

    return {"child": child, "caregiver": caregiver_paid,
            "total": child + caregiver_paid, "withheld": withheld}


# ----------------------------------------------------------------- the model --
@dataclass
class YearRow:
    year: int
    age: float
    status: str
    wages: float
    ss_total: float
    withdrawal: float
    taxable_sale: float
    housing_cost: float
    other_expenses: float
    total_tax: float
    marginal_fed: float
    mortgage_balance: float
    retirement_balance: float
    taxable_balance: float
    net_worth: float
    shortfall: float


class Projection:
    """
    strategy: one of
      'payoff'        - liquidate enough in year 1 to retire the mortgage
      'gap'           - withdraw only the annual cash-flow deficit
      'recast'        - partial paydown + recast, then gap-fund
      'bracket_fill'  - gap-fund, but top up to the chosen bracket ceiling while
                        MFJ/QSS brackets are available; surplus to taxable
      'taxable_first' - gap-fund, but spend taxable (stepped-up) assets first
    """

    def __init__(self, inp: Inputs, strategy: str):
        self.inp = inp
        self.strategy = strategy
        self.mort = Mortgage(inp.mortgage_balance, inp.mortgage_rate,
                             inp.mortgage_months_remaining)
        self.retirement = inp.inherited_401k_traditional
        self.roth = inp.inherited_401k_roth
        self.taxable = inp.taxable_brokerage + inp.life_insurance_proceeds
        self.basis = inp.taxable_basis + inp.life_insurance_proceeds
        self.cash = inp.emergency_cash
        self.home = inp.home_value
        self.rows: list[YearRow] = []
        self.lifetime_tax = 0.0
        self.lifetime_penalty = 0.0

    # -- helpers -------------------------------------------------------------
    def _housing_cost(self, year, age, mortgage_paid):
        inp, k = self.inp, (1 + self.inp.expense_inflation) ** (year - self.inp.start_year)
        ptax = inp.property_tax_annual * k
        if inp.apply_cobb_age62_school_exemption and age >= 62:
            ptax *= (1 - inp.cobb_school_share_of_property_tax)
        return mortgage_paid + ptax + inp.homeowners_insurance_annual * k

    def _sell_taxable(self, gross):
        """Sell `gross` from the taxable account pro-rata; returns realized gain."""
        gross = min(gross, self.taxable)
        if gross <= 0 or self.taxable <= 0:
            return 0.0, 0.0
        basis_frac = self.basis / self.taxable
        gain = gross * (1 - basis_frac)
        self.basis -= gross * basis_frac
        self.taxable -= gross
        return gross, gain

    # -- one year ------------------------------------------------------------
    def _year_cash(self, w, *, year, age, status, n_kids, wages, other_ord,
                   ss, expenses, taxable_gross, taxable_gain, divs):
        # Social Security: up to 85% of HER caregiver benefit is taxable once
        # other income is meaningful. The child's benefit is the child's own
        # income and is essentially never taxable, so it is excluded here.
        ss_taxable = ss["caregiver"] * .85
        t = taxes.total_tax(
            wages=wages, retirement_distribution=w,
            other_ordinary_income=other_ord + ss_taxable,
            qualified_dividends=divs, ltcg=taxable_gain, status=status, age=age,
            n_children=n_kids, year=year, inflation=self.inp.inflation,
            penalty_applies=self.inp.rolled_into_own_ira,
        )
        inflow = wages + other_ord + ss["total"] + w + taxable_gross + divs
        return inflow - t["total"] - expenses, t

    def _solve_withdrawal(self, need_fn, hi=4_000_000):
        lo = 0.0
        if need_fn(lo) >= 0:
            return 0.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if need_fn(mid) < 0:
                lo = mid
            else:
                hi = mid
        return hi

    def run(self):
        inp = self.inp
        for year in range(inp.start_year, inp.horizon_year + 1):
            i = year - inp.start_year
            age = inp.her_age_start + i
            status, n_kids = filing_status(year, inp)

            wages = inp.her_salary * (1 + inp.salary_growth) ** i if age < 65 else 0.0
            other_ord = inp.decedent_wages_2026 if year == inp.start_year else 0.0
            ss = social_security(year, inp, wages)

            # ---- strategy-specific mortgage events (year 1 only) ------------
            lump = 0.0
            if i == 0 and self.strategy == "payoff":
                lump = self.mort.balance
            elif i == 0 and self.strategy == "recast":
                lump = min(inp.recast_paydown_amount, self.mort.balance)

            divs = self.taxable * inp.taxable_dividend_yield

            # mortgage cash flow for the year, after any lump event
            mort_sim = copy.deepcopy(self.mort)
            if lump and self.strategy == "payoff":
                mort_sim.payoff()
            elif lump:
                mort_sim.recast(lump)
            mort_paid, _ = mort_sim.run_year()

            housing = self._housing_cost(year, age, mort_paid)
            other_exp = (inp.other_living_expenses_monthly * 12
                         * (1 + inp.expense_inflation) ** i)
            expenses = housing + other_exp + lump

            # ---- funding order ----------------------------------------------
            # Strategies that deliberately pre-pay tax (bracket_fill) park the
            # surplus in the taxable account, so they must also spend from it
            # first -- otherwise the model drains the 401(k) while cash sits idle.
            spend_taxable_first = self.strategy in ("taxable_first", "bracket_fill")
            taxable_gross = taxable_gain = 0.0
            if spend_taxable_first and self.taxable > 0:
                probe, _ = self._year_cash(
                    0, year=year, age=age, status=status, n_kids=n_kids,
                    wages=wages, other_ord=other_ord, ss=ss, expenses=expenses,
                    taxable_gross=0, taxable_gain=0, divs=divs)
                if probe < 0:
                    taxable_gross, taxable_gain = self._sell_taxable(-probe * 1.15)

            def need(w):
                return self._year_cash(
                    w, year=year, age=age, status=status, n_kids=n_kids,
                    wages=wages, other_ord=other_ord, ss=ss, expenses=expenses,
                    taxable_gross=taxable_gross, taxable_gain=taxable_gain,
                    divs=divs)[0]

            w = self._solve_withdrawal(need)

            # ---- bracket filling --------------------------------------------
            # The MFJ/QSS window is the only period with double-width brackets.
            # Once she drops to HOH (and later Single) the same dollar of
            # distribution costs materially more -- the "widow's penalty".
            if self.strategy == "bracket_fill" and status in ("mfj", "qss"):
                ceiling = taxes.bracket_ceiling(inp.bracket_fill_rate, status,
                                                year, inp.inflation)
                std = taxes._index(taxes.FED_STD_DEDUCTION_2026[status], year,
                                   inp.inflation)
                room = ceiling + std - (wages + other_ord + divs
                                        + ss["caregiver"] * .85)
                w = max(w, min(max(room, 0.0), self.retirement))

            w = min(w, self.retirement)

            # Fallback for every strategy: if the retirement account cannot
            # cover the year, tap the taxable account rather than book a
            # phantom shortfall.
            probe, _ = self._year_cash(
                w, year=year, age=age, status=status, n_kids=n_kids, wages=wages,
                other_ord=other_ord, ss=ss, expenses=expenses,
                taxable_gross=taxable_gross, taxable_gain=taxable_gain, divs=divs)
            if probe < 0 and self.taxable > 0:
                more_gross, more_gain = self._sell_taxable(-probe * 1.2)
                taxable_gross += more_gross
                taxable_gain += more_gain

            net, t = self._year_cash(
                w, year=year, age=age, status=status, n_kids=n_kids, wages=wages,
                other_ord=other_ord, ss=ss, expenses=expenses,
                taxable_gross=taxable_gross, taxable_gain=taxable_gain, divs=divs)

            shortfall = max(0.0, -net)
            surplus = max(0.0, net)

            # ---- commit ------------------------------------------------------
            self.mort = mort_sim
            self.retirement = max(0.0, self.retirement - w) * (1 + inp.expected_return)
            self.roth *= (1 + inp.expected_return)
            self.taxable = (self.taxable + surplus) * (1 + inp.expected_return - inp.taxable_dividend_yield)
            self.basis += surplus
            self.home *= (1 + inp.home_appreciation)
            self.lifetime_tax += t["total"]
            self.lifetime_penalty += t["penalty"]

            self.rows.append(YearRow(
                year=year, age=age, status=status, wages=wages,
                ss_total=ss["total"], withdrawal=w, taxable_sale=taxable_gross,
                housing_cost=housing, other_expenses=other_exp,
                total_tax=t["total"], marginal_fed=t["marginal_fed"],
                mortgage_balance=self.mort.balance,
                retirement_balance=self.retirement + self.roth,
                taxable_balance=self.taxable,
                net_worth=(self.retirement + self.roth + self.taxable + self.cash
                           + self.home - self.mort.balance),
                shortfall=shortfall))
        return self

    # -- summary --------------------------------------------------------------
    def summary(self):
        last = self.rows[-1]
        depleted = next((r.year for r in self.rows if r.retirement_balance <= 1), None)
        return {
            "strategy": self.strategy,
            "lifetime_tax": self.lifetime_tax,
            "lifetime_penalty": self.lifetime_penalty,
            "total_withdrawn": sum(r.withdrawal for r in self.rows),
            "peak_marginal_fed": max(r.marginal_fed for r in self.rows),
            "yr1_withdrawal": self.rows[0].withdrawal,
            "yr1_tax": self.rows[0].total_tax,
            "end_retirement": last.retirement_balance,
            "end_taxable": last.taxable_balance,
            "end_net_worth": last.net_worth,
            "retirement_depleted_year": depleted,
            "any_shortfall": any(r.shortfall > 1 for r in self.rows),
        }


STRATEGIES = {
    "payoff":        "A. Pay off the mortgage now",
    "gap":           "B. Annual gap-funding withdrawals",
    "recast":        "C. Partial paydown + recast",
    "taxable_first": "D. Spend stepped-up taxable assets first",
    "bracket_fill":  "E. Bracket-fill during MFJ/QSS window",
}


def run_all(inp: Optional[Inputs] = None):
    inp = inp or DEFAULT
    return {k: Projection(inp, k).run() for k in STRATEGIES}
