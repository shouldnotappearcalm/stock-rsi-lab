import unittest

from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, validate_bars, validate_dividends


class RawAccountCaptureTests(unittest.TestCase):
    def test_daily_capture_is_unadjusted_and_bounded_with_explicit_state(self):
        row = ["2024-01-02","sz.000050","10","11","9","10","10","1000","10000","3","1","0"]
        self.assertEqual(validate_bars("SZ000050",BAR_FIELDS,[row])[0]["adjustflag"],"3")
        for changes in ({"date":"2026-10-19"},{"code":"sh.600000"},{"adjustflag":"2"},{"tradestatus":""}):
            bad = dict(zip(BAR_FIELDS,row)) | changes
            with self.assertRaises(ValueError):
                validate_bars("SZ000050",BAR_FIELDS,[[bad[key] for key in BAR_FIELDS]])

    def test_corporate_capture_preserves_ambiguous_tax_text_and_quarantines_future(self):
        value = dict.fromkeys(DIVIDEND_FIELDS,"")
        value.update(code="sh.601288",dividPlanDate="2024-05-30",dividRegistDate="2024-06-06",
                     dividOperateDate="2024-06-07",dividPayDate="2024-06-07",
                     dividCashPsBeforeTax="0.2309",dividCashPsAfterTax="0.20781或0.2309",dividStocksPs="0.000000")
        rows, quarantine = validate_dividends("SH601288",DIVIDEND_FIELDS,[[value[key] for key in DIVIDEND_FIELDS]],2024)
        self.assertEqual(rows[0]["dividCashPsBeforeTax"],"0.2309")
        self.assertEqual(rows[0]["dividCashPsAfterTax"],"0.20781或0.2309")
        self.assertEqual(quarantine,[])
        value["dividOperateDate"] = "2026-10-19"
        rows, quarantine = validate_dividends("SH601288",DIVIDEND_FIELDS,[[value[key] for key in DIVIDEND_FIELDS]],2026)
        self.assertEqual(rows,[])
        self.assertEqual(quarantine[0]["reason"],"AFTER_CAPTURE_CUTOFF")
