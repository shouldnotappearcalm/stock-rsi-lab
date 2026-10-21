"""One new monthly risk overlay; the rejected Amihud seed stays unchanged.

TheCNY1 boundary is a research heuristic inspired by pre2024 exchange rules,
not a statutory20-day delisting classifier or a guarantee of executable exit.
"""
import copy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext

from stock_rsi.data import digest

CONTRACT = 'MONTHLY_RAW_CLOSE_1CNY_ORDINARY_GUARD_V1'
POLICY_ID = 'amihud22_monthly_price_risk1'
MIN_PRICE = Decimal('1.00')
BUDGET = Decimal('.95')
WEIGHT_QUANTUM = Decimal('1e-24')


def need(value, message):
    if not value:
        raise ValueError(message)


def number(value):
    need(type(value) in (str, int, float), 'explicit finite JSON numeric value required')
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid decimal source value') from None
    need(value.is_finite(), 'finite source value required')
    return value


def overlay_target(seed, formation_cells):
    need(type(seed) is dict and set(seed) == {'as_of', 'weights'}
         and type(seed['weights']) is dict and seed['weights'], 'original nonempty seed target required')
    need(type(seed['as_of']) is str, 'canonical formation date string required')
    asof = date.fromisoformat(seed['as_of'])
    need(asof.isoformat() == seed['as_of'] and '2023-12-29' <= seed['as_of'] <= '2025-12-31',
         'canonical pre2026 formation date required')
    weights = {code: number(w) for code, w in seed['weights'].items()}
    need(all(w > 0 for w in weights.values()) and abs(sum(weights.values()) - BUDGET) <= Decimal('1e-12'),
         'original positive95percent seed weights required')
    need(set(formation_cells) == set(weights), 'exact original selected formation cells required')
    blocked = {}
    for code in sorted(weights):
        row = formation_cells[code]
        need(set(row) == {'date', 'close', 'tradestatus', 'isST'} and row['date'] == seed['as_of'],
             'only exact formation-day cells may enter risk decision')
        need(row['tradestatus'] in ('0', '1') and row['isST'] in ('0', '1'),
             'known historical activity and ordinary/ST flags required')
        reasons = []
        if row['tradestatus'] == '0':
            reasons.append('KNOWN_FORMATION_HALT')
        else:
            close = number(row['close'])
            try:
                cent_price = close > 0 and close == close.quantize(Decimal('.01'))
            except InvalidOperation:
                cent_price = False
            need(cent_price, 'valid active raw cent close required')
            if close < MIN_PRICE:
                reasons.append('FORMATION_RAW_CLOSE_BELOW_CNY1')
        if row['isST'] == '1':
            reasons.append('KNOWN_FORMATION_ST_STATE')
        if reasons:
            blocked[code] = reasons
    retained = sorted(set(weights) - set(blocked))
    if not blocked:
        # A no-op overlay must not change the original economic weights.
        result_weights = copy.deepcopy(seed['weights'])
    elif not retained:
        # The original allocator requires a nonempty map: explicit zero weights
        # express cash and sell prior holdings without inventing new securities.
        result_weights = {code: '0' for code in sorted(weights)}
    else:
        total = sum(weights[code] for code in retained)
        allocated = {}
        with localcontext() as ctx:
            ctx.prec = 60
            for code in retained[:-1]:
                allocated[code] = (BUDGET * weights[code] / total).quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
            allocated[retained[-1]] = BUDGET - sum(allocated.values())
        need(all(w > 0 for w in allocated.values()) and sum(allocated.values()) == BUDGET,
             'exact95percent surviving allocation required')
        result_weights = {code: format(w, 'f') for code, w in allocated.items()}
    evidence = {'contract': CONTRACT, 'formation_asof': seed['as_of'],
                'original_seed_target': copy.deepcopy(seed), 'formation_cells': copy.deepcopy(formation_cells),
                'minimum_raw_close_CNY': str(MIN_PRICE), 'blocked': blocked, 'retained': retained}
    evidence_id = digest(evidence)
    target = {'as_of': seed['as_of'], 'weights': result_weights,
              'risk_overlay': {'contract': CONTRACT, 'formation_evidence_id': evidence_id}}
    receipt = {**evidence, 'formation_evidence_id': evidence_id,
               'result_weights': copy.deepcopy(result_weights), 'all_filtered_to_cash': not retained,
               'statutory_delisting_classifier': False, 'historical_arrival_verified': False}
    return target, receipt


def build_overlay_targets(seeds, calendar, read_formation):
    """The only provider requests are original names at the priorclose asof."""
    labels = [str(day) for day in calendar]
    need(labels == sorted(set(labels)), 'explicit sorted unique session calendar required')
    targets, receipts = {}, []
    for day, seed in sorted(seeds.items()):
        need('2024-01-02' <= day <= '2025-12-31' and day in labels, 'fixed pre2026 execution day required')
        index = labels.index(day)
        need(index > 0 and seed['as_of'] == labels[index - 1], 'immediate prior explicit close required')
        execution, formation = date.fromisoformat(day), date.fromisoformat(seed['as_of'])
        previous_month = (execution.year, execution.month - 1) if execution.month > 1 else (execution.year - 1, 12)
        need((formation.year, formation.month) == previous_month, 'original monthly formation cadence required')
        cells = {code: read_formation(code, seed['as_of']) for code in sorted(seed['weights'])}
        targets[day], receipt = overlay_target(seed, cells)
        receipts.append({'execution_session': day, **receipt})
    return targets, receipts
