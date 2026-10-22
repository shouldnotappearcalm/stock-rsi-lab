"""One conditional annual-GP hypothesis, with explicit source exclusions."""
from collections import Counter
from datetime import date, datetime, time
from fractions import Fraction
import math
from zoneinfo import ZoneInfo

from stock_rsi import annual_profitability as annual
from stock_rsi.prior_close_orders import AsOfPrices

PRIMARY = 'gp_assets_top_decile_conditional'
LOW_CONTROL = 'gp_assets_bottom_decile_control'
NAMES = (PRIMARY, 'eligible_equal_weight', LOW_CONTROL)
START, END = '2024-01-02', '2025-12-31'


def need(ok, why):
    if not ok:
        raise ValueError(why)


def minimum_fiscal_year(as_of):
    day = date.fromisoformat(as_of)
    return day.year - (2 if day.month <= 6 else 1)


def rank_decile(scores, *, lowest=False):
    need(scores and all(type(v) is Fraction for v in scores.values()), 'nonempty exact rational scores')
    return tuple(sorted(scores, key=lambda c: (scores[c] if lowest else -scores[c], c))[:max(1, len(scores)//10)])


def build_targets(snapshot, memberships, cohort, source_views, start=START, end=END, *, on_formation=None):
    need(START <= start <= end <= END, 'development source/quote boundary ends in2025')
    need(type(cohort) in (list, tuple) and len(set(cohort)) == len(cohort) and cohort,
         'complete unique initial source cohort')
    targets = {name: {} for name in NAMES}
    receipts = []
    for index, execution in enumerate(snapshot.calendar):
        if not start <= execution.isoformat() <= end:
            continue
        need(index > 0, 'preceding actual exchange session required')
        previous = snapshot.calendar[index-1]
        if execution.strftime('%Y-%m') == previous.strftime('%Y-%m'):
            continue
        clock = datetime.combine(previous, time(15, 5), ZoneInfo('Asia/Shanghai'))
        source = source_views[execution.isoformat()]
        need(annual.aware(source['as_of']) == clock and source['visibility_mode'] == annual.RECONSTRUCTED
             and source['cohort_count'] == len(cohort), 'exact current formation source view required')
        rows = source['classifications']
        need(len(rows) == len(cohort) and sorted(r['instrument'] for r in rows) == sorted(cohort),
             'every initial source name must appear exactly once')
        prices, scores, evidence, admission = AsOfPrices(snapshot, previous), {}, {}, []
        active = {c for c in cohort if any(a <= previous.isoformat() <= b for a, b in memberships.get(c, ())) }
        for row in rows:
            code, reason = row['instrument'], None
            if code not in active:
                reason = 'NOT_IN_FORMATION_MEMBERSHIP'
            elif row['industry_status'] != 'NONFINANCIAL_IN_SOURCE_VINTAGE':
                reason = 'NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif row['annual_status'] != 'LATEST_CURRENT_SOURCE_SUPPORTED_NOT_ADMITTED':
                reason = row['annual_status']
            elif row['latest_fiscal_year'] < minimum_fiscal_year(previous.isoformat()):
                reason = 'STALE_ANNUAL_SOURCE'
            if reason is not None:
                admission.append({'instrument': code, 'reason': reason})
                continue
            current = row['current_observation']; original = current['source']
            need(original['instrument'] == code and original['fiscal_end'] == f'{row["latest_fiscal_year"]}-12-31'
                 and original['payload']['column_role'] == 'CURRENT'
                 and original['payload']['document_sha256'] == row['selected_source_sha256']
                 and current['record_id'] == original['record_id'], 'same current financial-source identity')
            rebuilt = annual.snapshot_observations([original], clock.isoformat(), mode=annual.RECONSTRUCTED)['records']
            need(len(rebuilt) == 1 and rebuilt[0] == current, 'unaltered visible coherent current observation')
            cells = original['payload']['cells']
            amounts = {}
            for field in annual.FIELDS:
                cell = cells[field]
                amount = annual.amount_CNY(cell['literal'], cell['unit'])
                need(Fraction(cell['value_CNY']) == Fraction(amount), 'normalized source amount/literal agreement')
                amounts[field] = Fraction(amount)
            need(amounts['total_assets'] > 0 and amounts['revenue'] >= 0 and amounts['cost_of_sales'] >= 0,
                 'valid consolidated source amounts')
            values = [prices.value(code, field, previous.isoformat()) for field in ('close', 'volume', 'factor')]
            if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
                admission.append({'instrument': code, 'reason': 'NO_POSITIVE_FORMATION_QUOTE'})
                continue
            ratio = (amounts['revenue'] - amounts['cost_of_sales']) / amounts['total_assets']
            scores[code] = ratio
            evidence[code] = {'record_id': current['record_id'], 'source_sha256': row['selected_source_sha256'],
                              'fiscal_end': original['fiscal_end'], 'publication_day': original['publication_day'],
                              'score_fraction': str(ratio)}
            admission.append({'instrument': code, 'reason': 'CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'})
        need(len(scores) >= 100 and len(scores) >= .5 * len(active), 'conditional financial/price coverage below fixed structural gate')
        choices = {PRIMARY: rank_decile(scores), 'eligible_equal_weight': tuple(sorted(scores)),
                   LOW_CONTROL: rank_decile(scores, lowest=True)}
        for name, selected in choices.items():
            targets[name][execution.isoformat()] = {'as_of': previous.isoformat(),
                'weights': {code: .95 / len(selected) for code in selected}}
        receipts.append({'execution_session': execution.isoformat(), 'formation_asof': previous.isoformat(),
            'source_as_of': source['as_of'], 'initial_source_cohort': len(cohort), 'formation_members': len(active),
            'eligible': len(scores), 'minimum_fiscal_year': minimum_fiscal_year(previous.isoformat()),
            'cohort_admission': admission, 'admission_counts': dict(Counter(r['reason'] for r in admission)),
            'ranked_source': evidence, 'selections': choices, 'latest_factor_price_read': prices.latest_read.isoformat(),
            'source_availability': annual.RECONSTRUCTED, 'classification_vintage': '2021Q3',
            'historical_arrival_verified': False, 'current_business_identity_verified': False,
            'financial_reporting_compatibility_verified': False, 'investment_factor_admitted': False})
        if on_formation is not None:
            on_formation(execution.isoformat(), {name: targets[name][execution.isoformat()] for name in NAMES}, receipts[-1])
    return targets, receipts
