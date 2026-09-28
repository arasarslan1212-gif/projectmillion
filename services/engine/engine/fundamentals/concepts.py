"""Standard line items and the XBRL concepts that can carry them, in priority order.

Companies tag the same economic item with different us-gaap elements; the first concept in each
list that has data wins (per period). Units: "USD" money, "USD/shares" per-share, "shares" counts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    key: str
    label: str
    kind: str  # "duration" (flow) | "instant" (balance)
    unit: str
    concepts: tuple[str, ...]
    taxonomy: str = "us-gaap"
    statement: str = "income"  # income | balance | cashflow | other


def _li(key, label, kind, unit, concepts, statement, taxonomy="us-gaap") -> LineItem:
    return LineItem(key, label, kind, unit, tuple(concepts), taxonomy, statement)


LINE_ITEMS: dict[str, LineItem] = {
    li.key: li
    for li in [
        # ---- income statement --------------------------------------------------------
        _li(
            "revenue",
            "Revenue",
            "duration",
            "USD",
            [
                "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueNet",
                "SalesRevenueGoodsNet",
                "RevenuesNetOfInterestExpense",
                "OperatingLeasesIncomeStatementLeaseRevenue",
            ],
            "income",
        ),
        _li(
            "cost_of_revenue",
            "Cost of revenue",
            "duration",
            "USD",
            [
                "CostOfRevenue",
                "CostOfGoodsAndServicesSold",
                "CostOfGoodsSold",
                "CostOfServices",
            ],
            "income",
        ),
        _li("gross_profit", "Gross profit", "duration", "USD", ["GrossProfit"], "income"),
        _li(
            "rnd",
            "Research & development",
            "duration",
            "USD",
            [
                "ResearchAndDevelopmentExpense",
                "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            ],
            "income",
        ),
        _li(
            "sga",
            "Selling, general & administrative",
            "duration",
            "USD",
            [
                "SellingGeneralAndAdministrativeExpense",
                "GeneralAndAdministrativeExpense",
            ],
            "income",
        ),
        _li("operating_income", "Operating income", "duration", "USD", ["OperatingIncomeLoss"], "income"),
        _li(
            "interest_expense",
            "Interest expense",
            "duration",
            "USD",
            [
                "InterestExpense",
                "InterestExpenseNonoperating",
                "InterestExpenseDebt",
                "InterestAndDebtExpense",
            ],
            "income",
        ),
        _li(
            "pretax_income",
            "Pre-tax income",
            "duration",
            "USD",
            [
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            ],
            "income",
        ),
        _li("income_tax", "Income tax", "duration", "USD", ["IncomeTaxExpenseBenefit"], "income"),
        _li(
            "net_income",
            "Net income",
            "duration",
            "USD",
            [
                "NetIncomeLoss",
                "ProfitLoss",
                "NetIncomeLossAvailableToCommonStockholdersBasic",
            ],
            "income",
        ),
        _li(
            "eps_diluted",
            "Diluted EPS",
            "duration",
            "USD/shares",
            [
                "EarningsPerShareDiluted",
                "EarningsPerShareBasicAndDiluted",
            ],
            "income",
        ),
        _li("eps_basic", "Basic EPS", "duration", "USD/shares", ["EarningsPerShareBasic"], "income"),
        _li(
            "shares_diluted",
            "Diluted shares (weighted avg.)",
            "duration",
            "shares",
            [
                "WeightedAverageNumberOfDilutedSharesOutstanding",
            ],
            "income",
        ),
        _li(
            "shares_basic",
            "Basic shares (weighted avg.)",
            "duration",
            "shares",
            [
                "WeightedAverageNumberOfSharesOutstandingBasic",
            ],
            "income",
        ),
        _li(
            "sbc",
            "Stock-based compensation",
            "duration",
            "USD",
            [
                "ShareBasedCompensation",
                "AllocatedShareBasedCompensationExpense",
            ],
            "cashflow",
        ),
        _li(
            "dna",
            "Depreciation & amortization",
            "duration",
            "USD",
            [
                "DepreciationDepletionAndAmortization",
                "DepreciationAndAmortization",
                "DepreciationAmortizationAndAccretionNet",
                "Depreciation",
            ],
            "cashflow",
        ),
        # ---- banks -------------------------------------------------------------------
        _li(
            "interest_income",
            "Interest income",
            "duration",
            "USD",
            [
                "InterestAndDividendIncomeOperating",
                "InterestIncome",
            ],
            "income",
        ),
        _li(
            "net_interest_income",
            "Net interest income",
            "duration",
            "USD",
            ["InterestIncomeExpenseNet"],
            "income",
        ),
        _li("noninterest_income", "Noninterest income", "duration", "USD", ["NoninterestIncome"], "income"),
        _li(
            "noninterest_expense", "Noninterest expense", "duration", "USD", ["NoninterestExpense"], "income"
        ),
        _li(
            "provision",
            "Provision for credit losses",
            "duration",
            "USD",
            [
                "ProvisionForLoanLeaseAndOtherLosses",
                "ProvisionForLoanAndLeaseLosses",
                "ProvisionForCreditLosses",
            ],
            "income",
        ),
        # ---- insurers ----------------------------------------------------------------
        _li("premiums_earned", "Premiums earned", "duration", "USD", ["PremiumsEarnedNet"], "income"),
        _li(
            "losses_incurred",
            "Losses & benefits incurred",
            "duration",
            "USD",
            [
                "PolicyholderBenefitsAndClaimsIncurredNet",
                "IncurredClaimsPropertyCasualtyAndLiability",
            ],
            "income",
        ),
        _li(
            "underwriting_expense",
            "Underwriting & acquisition expense",
            "duration",
            "USD",
            [
                "DeferredPolicyAcquisitionCostAmortizationExpense",
                "OtherUnderwritingExpense",
            ],
            "income",
        ),
        # ---- REITs -------------------------------------------------------------------
        _li(
            "gain_on_sale_re",
            "Gain on sale of real estate",
            "duration",
            "USD",
            [
                "GainLossOnSaleOfRealEstateInvestmentProperty",
                "GainsLossesOnSalesOfInvestmentRealEstate",
            ],
            "income",
        ),
        _li(
            "re_acquisitions",
            "Real estate acquisitions",
            "duration",
            "USD",
            ["PaymentsToAcquireRealEstate"],
            "cashflow",
        ),
        # ---- balance sheet -----------------------------------------------------------
        _li(
            "cash",
            "Cash & equivalents",
            "instant",
            "USD",
            [
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "Cash",
            ],
            "balance",
        ),
        _li(
            "st_investments",
            "Short-term investments",
            "instant",
            "USD",
            [
                "ShortTermInvestments",
                "MarketableSecuritiesCurrent",
                "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
            ],
            "balance",
        ),
        _li(
            "receivables",
            "Accounts receivable",
            "instant",
            "USD",
            [
                "AccountsReceivableNetCurrent",
                "ReceivablesNetCurrent",
            ],
            "balance",
        ),
        _li("inventory", "Inventory", "instant", "USD", ["InventoryNet"], "balance"),
        _li("current_assets", "Current assets", "instant", "USD", ["AssetsCurrent"], "balance"),
        _li(
            "ppe",
            "PP&E, net",
            "instant",
            "USD",
            ["PropertyPlantAndEquipmentNet", "RealEstateInvestmentPropertyNet"],
            "balance",
        ),
        _li("goodwill", "Goodwill", "instant", "USD", ["Goodwill"], "balance"),
        _li(
            "intangibles",
            "Intangible assets",
            "instant",
            "USD",
            [
                "IntangibleAssetsNetExcludingGoodwill",
                "FiniteLivedIntangibleAssetsNet",
            ],
            "balance",
        ),
        _li("total_assets", "Total assets", "instant", "USD", ["Assets"], "balance"),
        _li("accounts_payable", "Accounts payable", "instant", "USD", ["AccountsPayableCurrent"], "balance"),
        _li(
            "current_liabilities", "Current liabilities", "instant", "USD", ["LiabilitiesCurrent"], "balance"
        ),
        _li(
            "debt_current",
            "Current debt",
            "instant",
            "USD",
            [
                "DebtCurrent",
                "LongTermDebtCurrent",
                "ShortTermBorrowings",
                "CommercialPaper",
            ],
            "balance",
        ),
        _li(
            "debt_noncurrent",
            "Long-term debt",
            "instant",
            "USD",
            [
                "LongTermDebtNoncurrent",
                "LongTermDebtAndCapitalLeaseObligations",
                "SeniorNotes",
            ],
            "balance",
        ),
        _li("debt_total", "Total debt (reported)", "instant", "USD", ["LongTermDebt"], "balance"),
        _li(
            "operating_lease_liab",
            "Operating lease liabilities",
            "instant",
            "USD",
            ["OperatingLeaseLiability"],
            "balance",
        ),
        _li("total_liabilities", "Total liabilities", "instant", "USD", ["Liabilities"], "balance"),
        _li(
            "liabilities_and_equity",
            "Liabilities & equity",
            "instant",
            "USD",
            ["LiabilitiesAndStockholdersEquity"],
            "balance",
        ),
        _li("equity", "Shareholders' equity", "instant", "USD", ["StockholdersEquity"], "balance"),
        _li(
            "equity_incl_nci",
            "Equity incl. noncontrolling interests",
            "instant",
            "USD",
            [
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ],
            "balance",
        ),
        _li(
            "minority_interest", "Noncontrolling interests", "instant", "USD", ["MinorityInterest"], "balance"
        ),
        _li(
            "retained_earnings",
            "Retained earnings",
            "instant",
            "USD",
            ["RetainedEarningsAccumulatedDeficit"],
            "balance",
        ),
        _li(
            "shares_outstanding",
            "Shares outstanding",
            "instant",
            "shares",
            ["CommonStockSharesOutstanding"],
            "balance",
        ),
        _li("deposits", "Deposits", "instant", "USD", ["Deposits"], "balance"),
        _li(
            "loans",
            "Loans, net",
            "instant",
            "USD",
            [
                "LoansAndLeasesReceivableNetReportedAmount",
                "LoansAndLeasesReceivableNetOfDeferredIncome",
                "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
            ],
            "balance",
        ),
        _li(
            "pension_funded_status",
            "Pension funded status",
            "instant",
            "USD",
            [
                "DefinedBenefitPlanFundedStatusOfPlan",
            ],
            "balance",
        ),
        # ---- cash flow ---------------------------------------------------------------
        _li(
            "cfo",
            "Operating cash flow",
            "duration",
            "USD",
            [
                "NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            ],
            "cashflow",
        ),
        _li(
            "capex",
            "Capital expenditures",
            "duration",
            "USD",
            [
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsToAcquireProductiveAssets",
                "PaymentsForCapitalImprovements",
            ],
            "cashflow",
        ),
        _li(
            "dividends_paid",
            "Dividends paid",
            "duration",
            "USD",
            [
                "PaymentsOfDividends",
                "PaymentsOfDividendsCommonStock",
            ],
            "cashflow",
        ),
        _li(
            "buybacks",
            "Share repurchases",
            "duration",
            "USD",
            ["PaymentsForRepurchaseOfCommonStock"],
            "cashflow",
        ),
        _li(
            "stock_issued",
            "Stock issued",
            "duration",
            "USD",
            ["ProceedsFromIssuanceOfCommonStock"],
            "cashflow",
        ),
        _li(
            "acquisitions",
            "Acquisitions",
            "duration",
            "USD",
            ["PaymentsToAcquireBusinessesNetOfCashAcquired"],
            "cashflow",
        ),
        _li(
            "dps",
            "Dividends per share (declared)",
            "duration",
            "USD/shares",
            [
                "CommonStockDividendsPerShareDeclared",
                "CommonStockDividendsPerShareCashPaid",
            ],
            "other",
        ),
        # ---- debt maturity ladder (reported in the 10-K debt footnote) ----------------
        _li(
            "debt_maturity_y1",
            "Debt due in 1 year",
            "instant",
            "USD",
            ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"],
            "other",
        ),
        _li(
            "debt_maturity_y2",
            "Debt due in year 2",
            "instant",
            "USD",
            ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"],
            "other",
        ),
        _li(
            "debt_maturity_y3",
            "Debt due in year 3",
            "instant",
            "USD",
            ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree"],
            "other",
        ),
        _li(
            "debt_maturity_y4",
            "Debt due in year 4",
            "instant",
            "USD",
            ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour"],
            "other",
        ),
        _li(
            "debt_maturity_y5",
            "Debt due in year 5",
            "instant",
            "USD",
            ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive"],
            "other",
        ),
        _li(
            "debt_maturity_after5",
            "Debt due after year 5",
            "instant",
            "USD",
            ["LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive"],
            "other",
        ),
        # ---- cover page (dei) --------------------------------------------------------
        _li(
            "shares_outstanding_cover",
            "Shares outstanding (cover page)",
            "instant",
            "shares",
            [
                "EntityCommonStockSharesOutstanding",
            ],
            "other",
            taxonomy="dei",
        ),
        _li(
            "public_float",
            "Public float (cover page)",
            "instant",
            "USD",
            ["EntityPublicFloat"],
            "other",
            taxonomy="dei",
        ),
        _li(
            "employees", "Employees", "instant", "pure", ["EntityNumberOfEmployees"], "other", taxonomy="dei"
        ),
    ]
}

# Line items fetched cross-sectionally via SEC frames for sector distributions.
FRAME_ITEMS = [
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "cfo",
    "capex",
    "dna",
    "sbc",
    "interest_expense",
    "total_assets",
    "current_assets",
    "current_liabilities",
    "total_liabilities",
    "equity",
    "cash",
    "debt_noncurrent",
    "debt_current",
    "shares_diluted",
    "retained_earnings",
    "receivables",
    "dividends_paid",
    "net_interest_income",
    "noninterest_income",
    "noninterest_expense",
    "deposits",
    "loans",
]
