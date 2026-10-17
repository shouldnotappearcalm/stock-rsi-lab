"""Small, fixed CNINFO announcement-availability pilot; no strategy returns.

The sample is determined by historical CSI500 membership and a fixed hash.
The current CNINFO organization lookup is used only to address pilot queries;
it is not an eligible point-in-time security master for a full backtest.
"""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AS_OF = "2024-01-02"
START = "2024-01-01"
END = "2025-12-31"
CNINFO = "https://www.cninfo.com.cn"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": CNINFO + "/"}
ANNUAL_CATEGORY = "category_ndbg_szsh"
CORRECTION_CATEGORY = "category_bcgz_szsh"
REPORT_CATEGORIES = {
    "annual": ANNUAL_CATEGORY,
    "q1": "category_yjdbg_szsh",
    "h1": "category_bndbg_szsh",
    "q3": "category_sjdbg_szsh",
}


def fixed_sample(instrument_text):
    active = set()
    for line in instrument_text.splitlines():
        code, start, end = line.split()
        if start <= AS_OF <= end and (code.startswith("SH60") or code.startswith("SZ00")):
            active.add(code)
    selected = []
    for prefix in ("SH60", "SZ00"):
        names = [code for code in active if code.startswith(prefix)]
        names.sort(key=lambda code: hashlib.sha256(
            ("cninfo-admission-20261016:" + code).encode()
        ).hexdigest())
        if len(names) < 6:
            raise ValueError("insufficient point-in-time main-board members")
        selected.extend(names[:6])
    return selected


def original_report(kind, title):
    import re

    endings = {
        "annual": r"年度报告",
        "q1": r"(?:第一季度|一季度)报告",
        "h1": r"半年度报告",
        "q3": r"(?:第三季度|三季度)报告",
    }
    return bool(re.search(r"20\d{2}年?" + endings[kind] + r"(?:全文)?$", title))


def publication_date(ms):
    return datetime.fromtimestamp(ms / 1000, timezone(timedelta(hours=8))).date().isoformat()


def request_json(url, payload=None):
    body = urlencode(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers=HEADERS)
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def query(org, code, category, start=START, end=END, max_pages=1, fetch=None):
    if not START <= start <= end <= END:
        raise ValueError("CNINFO query crossed pre-2026 pilot window")
    if fetch is None:
        fetch = request_json
    payload = {
        "pageNum": "1", "pageSize": "30", "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": f"{code},{org}", "searchkey": "", "secid": "",
        "category": category, "trade": "", "seDate": start + "~" + end,
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    data = fetch(CNINFO + "/new/hisAnnouncement/query", payload)
    total = int(data.get("totalAnnouncement", 0))
    pages = (total + 29) // 30
    if pages > max_pages:
        raise ValueError("pilot query exceeded its registered page cap")
    rows = data.get("announcements") or []
    for page in range(2, pages + 1):
        payload["pageNum"] = str(page)
        rows.extend(fetch(CNINFO + "/new/hisAnnouncement/query", payload).get("announcements") or [])
    records = []
    for row in rows:
        day = publication_date(row["announcementTime"])
        if not start <= day <= end:
            raise ValueError("announcement outside pre-2026 pilot")
        records.append({
            "code": row["secCode"], "title": row["announcementTitle"],
            "day": day, "timestamp_ms": row["announcementTime"],
            "announcement_id": row["announcementId"],
            "pdf_path": row.get("adjunctUrl"),
        })
    return records


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--csi500-instruments", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    sample = fixed_sample(Path(args.csi500_instruments).read_text())
    stock_list = request_json(CNINFO + "/new/data/szse_stock.json")["stockList"]
    org = {item["code"]: item["orgId"] for item in stock_list}
    if any(code[2:] not in org for code in sample + ["SZ000001"]):
        raise ValueError("current CNINFO organization list misses a sample stock")

    reports = {}
    for kind, category in REPORT_CATEGORIES.items():
        reports[kind] = []
        for code in sample:
            reports[kind].extend(query(org[code[2:]], code[2:], category))
    def full_both_years():
        return sum(all(
            any(row["code"] == code[2:] and row["day"].startswith(year)
                and original_report(kind, row["title"]) for row in reports[kind])
            for kind in REPORT_CATEGORIES for year in ("2024", "2025")
        ) for code in sample)

    before_fallback = full_both_years()
    category_rows = {kind: len(rows) for kind, rows in reports.items()}
    recovered = []
    for instrument in sample:
        code = instrument[2:]
        for kind in REPORT_CATEGORIES:
            for year in ("2024", "2025"):
                if any(row["code"] == code and row["day"].startswith(year)
                       and original_report(kind, row["title"]) for row in reports[kind]):
                    continue
                fallback = query(org[code], code, "", year + "-01-01", year + "-12-31", max_pages=20)
                matches = [row for row in fallback if original_report(kind, row["title"])]
                known_ids = {row["announcement_id"] for row in reports[kind]}
                for row in matches:
                    if row["announcement_id"] not in known_ids:
                        reports[kind].append(row)
                        recovered.append({"code": code, "kind": kind, "year": year,
                                          "announcement_id": row["announcement_id"]})
    correction = query(org["000001"], "000001", CORRECTION_CATEGORY)
    raw = {"sample": sample, "reports": reports, "fallback_recoveries": recovered,
           "correction_example_000001": correction}
    output.mkdir(parents=True)
    raw_path = output / "raw.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
    counts = {}
    for instrument in sample:
        code = instrument[2:]
        counts[code] = {}
        for kind, rows in reports.items():
            matched = [row for row in rows if row["code"] == code]
            counts[code][kind] = {
                "category_rows": len(matched),
                "original_reports_by_publication_year": {
                    year: sum(original_report(kind, row["title"]) and row["day"].startswith(year)
                              for row in matched)
                    for year in ("2024", "2025")
                },
            }
    midnight = all(
        datetime.fromtimestamp(row["timestamp_ms"] / 1000, timezone(timedelta(hours=8))).time().isoformat() == "00:00:00"
        for rows in reports.values() for row in rows
    )
    result = {
        "status": "DATA_ADMISSION_PILOT_ONLY",
        "historical_sample_asof": AS_OF, "fixed_sample": sample,
        "source": CNINFO + "/new/hisAnnouncement/query",
        "window": [START, END], "report_categories": REPORT_CATEGORIES,
        "counts": counts, "category_rows_before_fallback": category_rows,
        "report_rows_after_fallback": {kind: len(rows) for kind, rows in reports.items()},
        "stocks_with_all_report_types_both_years_before_fallback": before_fallback,
        "stocks_with_all_report_types_both_years": full_both_years(),
        "fallback_recoveries": recovered,
        "report_timestamps_all_midnight": midnight,
        "correction_example_rows": len(correction),
        "availability_rule": "date-only; treat as available after announcement-day close, never at 00:00",
        "current_organization_lookup_used": True,
        "current_lookup_is_historical_security_master": False,
        "2026_price_or_return_accessed": False,
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "counts"},
                     ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
