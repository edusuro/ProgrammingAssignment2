"""
ALL ASSUMPTIONS LIVE HERE.

Every value marked PLACEHOLDER is a guess used only to make the model run and to
show the *shape* of the answer. Replace each one with a real figure from the
intake checklist (INTAKE.md) before drawing any conclusion about dollars.

Nothing in taxes.py is an assumption; everything there is statute.
"""

from dataclasses import dataclass, field


@dataclass
class Inputs:
    # ---- people -------------------------------------------------------------
    her_age_start: float = 52                 # CONFIRMED (b. 1974)
    #   He was 50 at death, ~25 years short of his RMD age of 75, so
    #   nothing is forced out of the account until roughly 2051.
    child_age_start: int = 12                 # PLACEHOLDER
    start_year: int = 2026
    horizon_year: int = 2046                  # model through her age 72

    # ---- income -------------------------------------------------------------
    her_salary: float = 86_000                # CONFIRMED
    salary_growth: float = .03
    decedent_wages_2026: float = 80_000       # CONFIRMED: earned before death

    # ---- Social Security survivor benefits ---------------------------------
    # The single biggest item missing from the original framing.
    decedent_pia_monthly: float = 3_000       # PLACEHOLDER: his PIA at death
    model_social_security: bool = True
    ss_child_rate: float = .75                # child of deceased worker
    ss_caregiver_rate: float = .75            # surviving parent, child under 16
    ss_family_max_multiple: float = 1.75      # 150%-188% of PIA; 175% typical
    ss_earnings_test_exempt_2026: float = 24_480
    ss_child_benefit_end_age: int = 18        # 19 if still in high school
    ss_caregiver_benefit_end_child_age: int = 16

    # ---- house --------------------------------------------------------------
    mortgage_balance: float = 167_332         # CONFIRMED
    mortgage_rate: float = .0250              # CONFIRMED approx; escrow test consistent
    mortgage_months_remaining: int = 120      # CONFIRMED: ~10 years
    #   Client states the monthly payment is $2,205.16. That CANNOT be P&I:
    #   at 2.75% over 120 months, P&I on $167,332 is $1,596.53. For $2,205.16
    #   to be P&I the rate would have to be ~9.93%, or the term ~7 years.
    #   So $2,205.16 is PITI, and ~$608.63/mo of it is escrowed property tax
    #   and insurance -- which CONTINUES after the mortgage is paid off.
    home_value: float = 525_000               # PLACEHOLDER
    home_appreciation: float = .03
    property_tax_annual: float = 4_200        # PLACEHOLDER (Cobb County)
    homeowners_insurance_annual: float = 2_600  # PLACEHOLDER
    # Cobb County grants a 100% SCHOOL tax exemption at age 62, no income test.
    # School tax is typically ~55-60% of a Cobb bill.
    cobb_school_share_of_property_tax: float = .55
    apply_cobb_age62_school_exemption: bool = True

    # ---- other spending -----------------------------------------------------
    other_living_expenses_monthly: float = 4_800   # PLACEHOLDER, ex-housing
    expense_inflation: float = .025

    # ---- assets -------------------------------------------------------------
    inherited_401k_traditional: float = 611_411    # CONFIRMED per TIAA letter
    #   $8,523.15 CREF + $602,887.78 mutual funds, valued 07/20/2026.
    #   No TIAA Traditional, so no ten-year payout constraint; fully liquid.
    inherited_401k_roth: float = 0                 # PLACEHOLDER
    taxable_brokerage: float = 50_000              # PLACEHOLDER, stepped-up basis
    taxable_basis: float = 50_000                  # = value at date of death
    emergency_cash: float = 25_000                 # PLACEHOLDER
    life_insurance_proceeds: float = 0             # PLACEHOLDER: tax-free if any

    # ---- markets ------------------------------------------------------------
    expected_return: float = .06              # nominal, balanced portfolio
    taxable_dividend_yield: float = .018
    inflation: float = .025

    # ---- account structure --------------------------------------------------
    # False = keep beneficiary/inherited status -> IRC 72(t)(2)(A)(ii) death
    # exception applies, no 10% penalty at any age.
    # True  = rolled into HER OWN IRA -> 10% penalty until 59.5.
    rolled_into_own_ira: bool = False

    # ---- strategy knobs -----------------------------------------------------
    recast_paydown_amount: float = 150_000    # strategy C
    bracket_fill_rate: float = .22            # strategy D: fill through 22%
    min_cash_buffer: float = 15_000

    def __post_init__(self):
        assert self.taxable_basis <= self.taxable_brokerage * 1.0001


DEFAULT = Inputs()
