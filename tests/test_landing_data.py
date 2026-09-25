"""Inputs of the landing page: AMFI's market-cap list (pipeline/amfi.py) and the exchanges' industry
classification (pipeline/industry.py). No network: parsers run on built or recorded responses."""
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import amfi  # noqa: E402
import industry  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def xlsx(rows):
    """A minimal one-sheet workbook with AMFI's layout (strings go to the shared-string table)."""
    ss, xml_rows = [], []
    for i, row in enumerate(rows, 1):
        cells = []
        for j, v in enumerate(row):
            ref = "ABCDEFGHIJK"[j] + str(i)
            if v is None:
                continue
            if isinstance(v, str):
                ss.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{len(ss) - 1}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in ss) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(xml_rows)}</sheetData></worksheet>")
    return b.getvalue()


HEAD = ["Sr. No.", "Company name", "ISIN", "BSE Symbol", "BSE 6 month Avg Total Market Cap in (Rs. Crs.)",
        "NSE Symbol", "NSE 6 month Avg Total Market Cap (Rs. Crs.)", "MSEI Symbol",
        "MSEI 6 month Avg Total Market Cap in (Rs Crs.)", "Average of All Exchanges (Rs. Cr.)",
        "Categorization as per SEBI Circular dated Oct 6, 2017"]


class AmfiTest(unittest.TestCase):
    def test_parse(self):
        title, basis, rows = amfi.parse(xlsx([
            ["Average Market Capitalization of listed companies during the six months ended 30 June 2026"], HEAD,
            ["1", "Reliance Industries Ltd", "INE002A01018", "RELIANCE", 1873294.7, "RELIANCE", 1873278.8, "-", None, 1873286.7750478899, "Large Cap"],
            ["2", "BSE  Ltd.", "INE118H01025", "-", None, "BSE", 134291.28, "-", None, 134291.2776, "Large Cap"]]))
        self.assertIn("30 June 2026", title)
        self.assertEqual(basis, "Categorization as per SEBI Circular dated Oct 6, 2017")
        self.assertEqual(rows[0], [1, "Reliance Industries Ltd", "INE002A01018", "RELIANCE", "RELIANCE", 1873286.78, "Large Cap"])
        self.assertEqual(rows[1][1:5], ["BSE Ltd.", "INE118H01025", None, "BSE"])  # '-' = not listed there
        amfi.check(rows)

    def test_check_rejects_a_category_off_the_rank(self):
        rows = [[1, "A", "I1", "A", "A", 300.0, "Large Cap"], [2, "B", "I2", "B", "B", 200.0, "Mid Cap"]]
        with self.assertRaises(AssertionError):
            amfi.check(rows)

    def test_committed_list(self):
        rec = json.loads((ROOT / "pipeline" / "inputs" / "amfi_mcap.json").read_text())
        rows = rec["rows"]
        amfi.check(rows)  # SEBI's rule holds on the file the site is built from
        self.assertEqual(sum(r[6] == "Large Cap" for r in rows), 100)
        self.assertEqual(sum(r[6] == "Mid Cap" for r in rows), 150)
        self.assertTrue(rec["source"].startswith("https://portal.amfiindia.com/"))


class IndustryTest(unittest.TestCase):
    def test_nse(self):
        body = json.dumps({"info": {"symbol": "RELIANCE"}, "industryInfo": {
            "macro": "Energy", "sector": "Oil Gas & Consumable Fuels", "industry": "Petroleum Products",
            "basicIndustry": "Refineries & Marketing"}}).encode()
        self.assertEqual(industry.nse_class(body),
                         ["Energy", "Oil Gas & Consumable Fuels", "Petroleum Products", "Refineries & Marketing"])
        self.assertIsNone(industry.nse_class(json.dumps({"industryInfo": {"macro": "-", "sector": ""}}).encode()))
        self.assertIsNone(industry.nse_class(b"{}"))

    def test_bse(self):
        # BSE's company header for Hero MotoCorp (scrip 500182), as archived by the Wayback Machine on 4 Jul 2024.
        body = (FIX / "bse_comheader_500182.json").read_bytes()
        self.assertEqual(industry.bse_class(body),
                         ["Consumer Discretionary", "Automobile and Auto Components", "Automobiles", "2/3 Wheelers"])

    def test_refusal(self):
        self.assertTrue(industry._refused(403, b"<HTML><HEAD><TITLE>Access Denied</TITLE>"))
        self.assertTrue(industry._refused(200, b"<!doctype html><html>"))
        self.assertFalse(industry._refused(200, b'{"industryInfo": {}}'))


if __name__ == "__main__":
    unittest.main()
