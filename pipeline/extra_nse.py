"""National Stock Exchange of India Ltd (NSE): a listing snapshot page, until its first quarterly filings.

    python3 pipeline/extra_nse.py

NSE listed on BSE only on 24 Sep 2026 (an exchange cannot list on itself), so it is outside the Nifty
indices and NSE's own daily files. Everything here comes from its Red Herring Prospectus dated
10 Sep 2026 (RHP, pages cited) and BSE's daily file; nothing is estimated. Post-offer holdings of the
selling shareholders are pre-offer shares minus the shares each offered (Annexure A, p.623): the issue
was subscribed 5.71 times, so every offered share was sold.

Writes src/co/NSE.json (a "snapshot" page), src/univ_extra.json (its universe row) and
pipeline/inputs/px_extra.json (its price feed for pipeline/live.py: BSE, matched by ISIN).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RHP = "https://investmentbank.kotak.com/kib-cms/sites/default/files/offer-documets/National%20Stock%20Exchange%20of%20India%20Limited%20-%20RHP_vf.pdf"
SHARES = 2_475_000_000

# RHP p.121: shareholders holding 1% or more of the pre-Offer capital (beneficiary position, 8 Sep 2026),
# with the shares each offered in the Offer for Sale (Annexure A, p.623; 0 = not a selling shareholder).
HOLDERS = [
    ("Life Insurance Corporation of India", "Indian insurer", "IN", 265_275_000, 0),
    ("Aranda Investments (Mauritius) Pte Ltd", "Foreign investor (Temasek group)", "MU", 112_463_356, 11_246_336),
    ("Stock Holding Corporation of India Limited", "Indian company (state-owned)", "IN", 110_000_000, 6_187_500),
    ("SBI Capital Markets Limited", "Indian bank group", "IN", 107_250_000, 8_780_590),
    ("Mahagony Limited", "Foreign investor", "MU", 92_295_000, 3_000_000),
    ("State Bank of India", "Indian bank group", "IN", 79_847_050, 15_969_410),
    ("PI Opportunities Fund I", "Indian fund (AIF)", "IN", 58_200_000, 0),
    ("Crown Capital Limited", "Foreign investor", "MU", 51_355_465, 5_871_093),
    ("DVI Fund (Mauritius) Limited", "Foreign investor", "MU", 45_216_215, 0),
    ("TIMF Holdings", "Foreign investor", "MU", 43_230_357, 0),
    ("General Insurance Corporation of India", "Indian insurer", "IN", 40_700_000, 6_187_500),
    ("Canada Pension Plan Investment Board", "Foreign pension fund", "CA", 39_580_200, 11_874_060),
    ("Radhakishan Shivkishan Damani", "Individual", "IN", 39_084_400, 0),
    ("National Insurance Company Limited", "Indian insurer", "IN", 35_200_000, 4_000_000),
    ("The New India Assurance Company Ltd.", "Indian insurer", "IN", 35_200_000, 10_500_000),
    ("The Oriental Insurance Company Limited", "Indian insurer", "IN", 35_200_000, 4_957_000),
    ("TA Asia Pacific Acquisitions Limited", "Foreign investor", "MU", 34_266_085, 2_000_000),
    ("MS Strategic (Mauritius) Limited", "Foreign investor", "MU", 29_760_000, 11_000_000),
    ("2726247 Ontario Inc.", "Foreign investor", "CA", 27_006_430, 5_401_286),
    ("Rimco (Mauritius) Limited", "Foreign investor", "MU", 24_750_000, 0),
]
# Selling shareholders below 1% pre-offer (Annexure A): shares offered.
OTHER_SELLERS = [
    ("Bank of Baroda", 7_690_375), ("United India Insurance Company Limited", 6_000_000),
    ("ICICI Lombard General Insurance Company Limited", 2_350_000), ("Soach Global Strategic Holdings Ltd.", 1_650_000),
    ("Indian Bank", 1_500_000), ("Be-In Eight s.r.l.", 262_500), ("Rajiv Bolla", 7_500),
    ("Shaik Samdani Basha", 1_000), ("Mahesh Gupta", 500),
]
OFFERED_TOTAL = 126_436_650

# Restated consolidated financials, RHP p.81-83 (₹ million -> ₹ crore). PAT = attributable to owners; EPS basic
# and diluted, continuing + discontinued, face value ₹1 (FY24 restated for the 4:1 bonus of 4 Nov 2024).
ANNUAL = {"q": ["FY24", "FY25", "FY26"], "rev": [14780.01, 17140.68, 16601.31],
          "pat": [8305.66, 12187.94, 10302.06], "eps": [33.56, 49.24, 41.62]}
QUARTER = {"q": ["Q1 FY26", "Q1 FY27"], "d": ["Jun-25", "Jun-26"], "rev": [4032.24, 4560.41],
           "pat": [2923.85, 3120.08], "eps": [11.81, 12.61]}
EQUITY = {"2025-06-30": 33331.49, "2026-06-30": 35244.23}  # equity attributable to owners, ₹ crore (p.80)


def main():
    for h in HOLDERS:  # every share count must reproduce the RHP's percentage (p.121)
        assert 0 <= h[4] <= h[3], h
    assert sum(h[4] for h in HOLDERS) + sum(s for _, s in OTHER_SELLERS) == OFFERED_TOTAL
    for p, e in zip(ANNUAL["pat"] + QUARTER["pat"], ANNUAL["eps"] + QUARTER["eps"]):
        assert abs(p * 1e7 / SHARES / e - 1) < 0.005, (p, e)  # EPS x shares = PAT to owners
    ttm = round(QUARTER["pat"][1] + ANNUAL["pat"][2] - QUARTER["pat"][0], 2)
    ttm_eps = round(QUARTER["eps"][1] + ANNUAL["eps"][2] - QUARTER["eps"][0], 2)
    roe = round(100 * ttm / ((EQUITY["2025-06-30"] + EQUITY["2026-06-30"]) / 2), 1)
    bvps = round(EQUITY["2026-06-30"] * 1e7 / SHARES, 2)
    holders = [dict(n=n, c=c, cty=cty, pre=pre, sold=sold, post=pre - sold) for n, c, cty, pre, sold in HOLDERS]
    D = {
        "snapshot": True,
        "co": {"s": "NSE", "n": "National Stock Exchange of India Ltd", "isin": "INE721I01024", "bse": "544937",
               "sector": "Financial Services", "industry": "Capital Markets", "bb": False, "oq": False,
               "exch": "BSE", "listed": "2026-09-24", "ipo_price": 1785.0, "shares_now": SHARES, "px_end": "2026-09-24",
               "fil": "2026-09-08", "ca": []},
        "tot": SHARES,
        # the one pre-listing pattern (RHP p.119): Public (B) and Trading Members and their Associates (C3)
        "pattern": {"date": "2026-09-08", "holders_count": 231_378, "public": 1_670_555_049, "c3": 804_444_951,
                    "src": RHP + " (p.119-120)"},
        "ipo": {"price": 1785.0, "band": [1700.0, 1785.0], "offered": OFFERED_TOTAL, "type": "Offer for sale",
                "size_cr": round(OFFERED_TOTAL * 1785 / 1e7, 2), "subscription": 5.71, "open": "2026-09-17",
                "close": "2026-09-21", "listed": "2026-09-24", "exchange": "BSE", "listing_open": 1800.0,
                "src": RHP + " (cover, p.623); subscription and dates: exchange data as reported on 24 Sep 2026"},
        "holders": holders, "other_sellers": [dict(n=n, sold=s) for n, s in OTHER_SELLERS],
        "earn_annual": ANNUAL, "earn_q": QUARTER,
        "val": {"bvps": bvps, "bs_date": "2026-06-30", "equity_cr": EQUITY["2026-06-30"], "roe": roe,
                "roe_basis": "TTM PAT to owners ÷ average equity (Jun-25, Jun-26)", "dps": 35.0,
                "dps_note": "FY26 final dividend ₹35 per share incl. a ₹10 special (approved 24 Aug 2026)",
                "ttm_pat": ttm, "ttm_eps": ttm_eps},
        "px_series": [["2026-09-24", 1818.0, 1878.0, 1800.0]],  # BSE daily file, 24 Sep 2026 (listing day)
        "bench": {"nifty50": {}, "nifty500": {}, "override": {}},
        "gates": [], "tiers": {}, "rec": [], "flag": [], "gen": "2026-09-25T06:00:00",
        "src": RHP,
    }
    (ROOT / "src" / "co" / "NSE.json").write_text(json.dumps(D, separators=(",", ":"), ensure_ascii=False))
    univ = [{"s": "NSE", "n": "National Stock Exchange of India Ltd", "m": round(SHARES * 1818.0 / 1e7), "p": 1818.0,
             "q": None, "pr": 0.0, "fi": None, "di": None, "h": len(holders), "fl": 0, "ok": True,
             "sh": 231_378, "f": "2026-09-08", "shares": SHARES, "shares_now": SHARES, "dash": True, "idx": [],
             "extra": True, "exch": "BSE"}]
    (ROOT / "src" / "univ_extra.json").write_text(json.dumps(univ, separators=(",", ":")))
    (ROOT / "pipeline" / "inputs" / "px_extra.json").write_text(json.dumps(
        {"NSE": {"shares": SHARES, "qbase_close": None, "bonus_events": [], "exch": "BSE", "isin": "INE721I01024"}}, indent=1))
    print(f"NSE snapshot: TTM PAT ₹{ttm} cr, EPS {ttm_eps}, ROE {roe}%, BVPS {bvps}; {len(holders)} holders ≥1%")


if __name__ == "__main__":
    main()
