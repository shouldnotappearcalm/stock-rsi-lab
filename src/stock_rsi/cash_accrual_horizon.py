"""Unchanged cash-accrual hypothesis through the fixed2026 horizon.

A reconstructed-publication daily research screen, not historical-arrival proof.
"""
from collections import Counter, defaultdict
from datetime import datetime, time
from fractions import Fraction
import math
from zoneinfo import ZoneInfo

from stock_rsi import annual_cash_accruals_v3 as cash
from stock_rsi.industry_catalog import snapshot_catalog, ARCHIVE_RECONSTRUCTED
from stock_rsi.gross_profitability_monthly import minimum_fiscal_year, rank_decile
from stock_rsi.prior_close_orders import AsOfPrices

PRIMARY = 'cn_total_ni_minus_cfo_mean_assets_bottom_decile'
HIGH_CONTROL = 'cn_total_ni_minus_cfo_mean_assets_top_decile_control'
NAMES = (PRIMARY, 'eligible_equal_weight', HIGH_CONTROL)
START, END = '2024-01-02', '2026-10-21'
SUPPORTED = 'CASH_ACCRUAL_CELLS_SUPPORTED_PENDING_SOURCE_QA'
FAILURES = ('CASH_ACCRUAL_SOURCE_SCHEMA_UNSUPPORTED', 'COVER_IDENTITY_UNVERIFIED')


def visible_latest(documents, cohort, as_of, *, mode=cash.RECONSTRUCTED):
    """Select latest editions using metadata only, including failed newer editions."""
    cash.need(mode in (cash.OBSERVED, cash.RECONSTRUCTED), 'explicit visibility mode')
    clock = cash.aware(as_of)
    cash.need(clock.astimezone(ZoneInfo('Asia/Shanghai')).year <= 2026, 'development ends in2026')
    cash.need(cohort and len(cohort) == len(set(cohort)), 'complete unique source cohort')
    visible = defaultdict(list)
    keys = set()
    for d in documents:
        year, public, observed = cash.metadata(d)
        cash.need(d['capture_key'] not in keys, 'unique original edition key')
        keys.add(d['capture_key'])
        if d['instrument'] not in cohort or clock < (max(public, observed) if mode == cash.OBSERVED else public):
            continue
        visible[d['instrument']].append(d)
    result = {}
    for code in cohort:
        editions = visible[code]
        if not editions:
            result[code] = (None, 'NO_VISIBLE_ANNUAL_REPORT')
            continue
        latest = max((d['effective_fiscal_year'], d['day']) for d in editions)
        latest_editions = [d for d in editions if (d['effective_fiscal_year'], d['day']) == latest]
        if len({d['source_sha256'] for d in latest_editions}) != 1:
            result[code] = (None, 'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS')
            continue
        chosen = min(latest_editions, key=lambda d: (int(d['announcement_id']), d['capture_key']))
        result[code] = (chosen, None)
    return result


def observation(document, case_reader, approved_ids, as_of, *, mode=cash.RECONSTRUCTED):
    """Neither case nor financial payload is read before its visibility gate."""
    year, public, observed = cash.metadata(document)
    clock = cash.aware(as_of)
    cash.need(mode in (cash.OBSERVED, cash.RECONSTRUCTED), 'explicit visibility mode')
    if clock < (max(public, observed) if mode == cash.OBSERVED else public):
        return None
    case = case_reader(document['capture_key'])
    cash.need(all(case[k] == document[d] for k,d in (
        ('capture_key','capture_key'),('instrument','instrument'),('fiscal_year','effective_fiscal_year'),
        ('publication_day','day'),('source_sha256','source_sha256'))), 'selected original case identity')
    cash.need(case['investment_factor_admitted'] is False and case['historical_arrival_verified'] is False,
              'source support does not grant investment or historical assurances')
    if case['status'] in FAILURES:
        cash.need(case['report'] is None and approved_ids[document['capture_key']] is None,
                  'unsupported latest edition cannot supply a financial value')
        return None
    cash.need(case['status'] == SUPPORTED, 'registered source status')
    report = cash.visible_report(document, as_of, lambda: case['report'], mode)
    cash.need(report['record_id'] == approved_ids[document['capture_key']], 'approved whole source record')
    parsed = report['parsed']; current, prior = f'{year}-12-31', f'{year-1}-12-31'
    def amount(cell):
        value = cash.v1.op.amount_CNY(cell['literal'], cell['unit'])
        cash.need(value.is_finite() and cell['value_CNY'] == format(value,'f'), 'literal/unit normalization')
        return Fraction(value)
    ni = amount(parsed['income'][current]['net_profit'])
    cfo = amount(parsed['cashflows'][current]['operating_cashflow'])
    begin, end = (amount(parsed['balances'][p]) for p in (prior,current))
    cash.need(begin > 0 and end > 0, 'positive explicit same-edition beginning and ending assets')
    score = (ni-cfo) / ((begin+end)/2)
    return {'instrument':document['instrument'], 'capture_key':document['capture_key'],
            'record_id':report['record_id'], 'source_sha256':document['source_sha256'],
            'publication_day':document['day'], 'current_fiscal_end':current,
            'score_fraction':str(score), 'net_profit_CNY':str(ni), 'operating_cashflow_CNY':str(cfo),
            'beginning_assets_CNY':str(begin), 'ending_assets_CNY':str(end),
            'historical_arrival_verified':False, 'investment_factor_admitted':False}


def known_amendment_blocks(document, amendments, as_of):
    clock = cash.aware(as_of)
    for a in amendments:
        if a['instrument'] != document['instrument'] or a['capture_key'] != document['capture_key']:
            continue
        public = cash.v1.datetime.combine(cash.v1.date.fromisoformat(a['publication_day']),
                                         cash.v1.time.max, ZoneInfo('Asia/Shanghai'))
        cash.need(cash.aware(a['captured_at_utc']) >= public, 'known amendment chronology')
        if clock >= public:
            return True
    return False


def build_targets(snapshot, memberships, cohort, documents, case_reader, approved_ids, industry,
                  amendments, start=START, end=END, *, on_formation=None):
    cash.need(START <= start <= end <= END, 'development window ends in2026')
    targets = {n:{} for n in NAMES}; receipts=[]
    for i, execution in enumerate(snapshot.calendar):
        if not start <= execution.isoformat() <= end:
            continue
        cash.need(i > 0, 'actual preceding exchange session required')
        previous = snapshot.calendar[i-1]
        if previous.strftime('%Y-%m') == execution.strftime('%Y-%m'):
            continue
        clock = datetime.combine(previous,time(15,5),ZoneInfo('Asia/Shanghai')).isoformat()
        latest = visible_latest(documents,cohort,clock)
        catalog = snapshot_catalog(industry,cohort,clock,mode=ARCHIVE_RECONSTRUCTED)
        sectors = {r['instrument']:r['status'] for r in catalog['classifications']}
        active = {c for c in cohort if any(a <= previous.isoformat() <= b for a,b in memberships.get(c,()))}
        prices = AsOfPrices(snapshot,previous); scores={}; evidence={}; admission=[]
        for code in sorted(cohort):
            d, reason = latest[code]
            if code not in active: reason='NOT_IN_FORMATION_MEMBERSHIP'
            elif sectors[code] != 'NONFINANCIAL_IN_SOURCE_VINTAGE': reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif d is not None and d['effective_fiscal_year'] < minimum_fiscal_year(previous.isoformat()): reason='STALE_ANNUAL_SOURCE'
            elif d is not None and known_amendment_blocks(d,amendments,clock): reason='UNRESOLVED_VISIBLE_KNOWN_AMENDMENT'
            if reason is None:
                o = observation(d,case_reader,approved_ids,clock)
                if o is None: reason='LATEST_SOURCE_UNSUPPORTED'
                else:
                    quotes=[prices.value(code,f,previous.isoformat()) for f in ('close','volume','factor')]
                    if any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in quotes): reason='NO_POSITIVE_FORMATION_QUOTE'
                    else:
                        scores[code]=Fraction(o['score_fraction']); evidence[code]=o
                        reason='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'
            admission.append({'instrument':code,'reason':reason})
        receipt={'execution_session':execution.isoformat(),'formation_asof':previous.isoformat(),
                 'source_as_of':clock,'initial_source_cohort':len(cohort),'formation_members':len(active),
                 'eligible':len(scores),'minimum_eligible':100,'coverage_pass':len(scores)>=100,
                 'admission_counts':dict(Counter(r['reason'] for r in admission)), 'cohort_admission':admission,
                 'ranked_source':evidence,'selections':{}, 'latest_factor_price_read':None if prices.latest_read is None else prices.latest_read.isoformat(),
                 'historical_arrival_verified':False,'financial_version_history_complete':False,
                 'current_business_identity_verified':False,'investment_factor_admitted':False}
        if len(scores) >= 100:
            selections={PRIMARY:rank_decile(scores,lowest=True), 'eligible_equal_weight':tuple(sorted(scores)),
                        HIGH_CONTROL:rank_decile(scores)}
            receipt['selections']=selections
            for n,selected in selections.items():
                targets[n][execution.isoformat()]={'as_of':previous.isoformat(),'weights':{c:.95/len(selected) for c in selected}}
        receipts.append(receipt)
        if on_formation is not None:
            on_formation(execution.isoformat(),{n:targets[n].get(execution.isoformat()) for n in NAMES},receipt)
    # All formation coverage is retained before failure; never backfill with older reports or partial-month cash.
    cash.need(receipts and all(r['coverage_pass'] for r in receipts), 'cash-accrual source coverage below fixed100-name guard; no account run')
    return targets, receipts
