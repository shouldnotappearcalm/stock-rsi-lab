"""Evidence-bound SSE risk-warning engineering adapter, separate from old policy.

Callers authenticate original rule/issuer document bytes. This module checks
metadata and clocks; conservative engineering availability is not actual arrival.
It never changes a target, share quantity, holding, tax rule or allocator.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import PurePath
import re

from stock_rsi.broker import money
from stock_rsi.calendar import SHANGHAI
from stock_rsi.data import digest
from stock_rsi.lifecycle_source_rows import source_rows_on
from stock_rsi.time import iso, parse_time

CONTRACT='SSE_MAINBOARD_RISK_WARNING_PRE2026_V1'
CENT=Decimal('.01')
RULE_FIELDS={'source_file','sha256','published_on','valid_from','valid_through'}
STATE_FIELDS={'instrument','exchange','board','risk_status','effective_from','effective_through',
              'published_on','engineering_available_at','actual_arrival_verified','source_file','source_sha256'}
PREOPEN_FIELDS=('date','code','preclose','tradestatus','isST','adjustflag')
PHASE_FIELDS={'PREOPEN':PREOPEN_FIELDS,'OPEN':(*PREOPEN_FIELDS,'open'),
              'CLOSE':(*PREOPEN_FIELDS,'open','high','low','close','volume','amount')}


def _day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('canonical regime date required')
    return date.fromisoformat(value)


def _document(name,sha):
    if (not isinstance(name,str) or not name or PurePath(name).name!=name or '\\' in name
            or name in ('.','..') or not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha)):
        raise ValueError('original document basename and SHA256 required')


def _validate_evidence(evidence,day,as_of):
    if (not isinstance(evidence,dict) or set(evidence)!={'contract','rule_document','state_intervals','account_capabilities'}
            or evidence['contract']!=CONTRACT or type(day) is not date):
        raise ValueError('supported explicit trading regime evidence required')
    at=parse_time(as_of);local=at.astimezone(SHANGHAI)
    rule=evidence['rule_document'];caps=evidence['account_capabilities']
    if not isinstance(rule,dict) or set(rule)!=RULE_FIELDS:
        raise ValueError('complete rule document metadata required')
    _document(rule['source_file'],rule['sha256'])
    start,end=_day(rule['valid_from']),_day(rule['valid_through'])
    if ([rule['valid_from'],rule['valid_through']]!=['2023-12-29','2025-12-31']
            or _day(rule['published_on'])>start or not start<=day<=end or local.date()!=day):
        raise ValueError('rule validity or as-of session changed')
    if (not isinstance(caps,dict) or set(caps)!={'risk_warning_buy_permission'}
            or type(caps['risk_warning_buy_permission']) is not bool):
        raise ValueError('explicit boolean account permission capability required')
    intervals=evidence['state_intervals']
    if not isinstance(intervals,list):raise ValueError('explicit source intervals required')
    grouped={}
    for state in intervals:
        if (not isinstance(state,dict) or set(state)!=STATE_FIELDS
                or not isinstance(state['instrument'],str)
                or not re.fullmatch(r'SH(?:600|601|603|605)[0-9]{3}',state['instrument'])
                or state['exchange']!='SSE' or state['board']!='MAINBOARD'
                or state['risk_status']!='OTHER_RISK_WARNING' or state['actual_arrival_verified'] is not False):
            raise ValueError('supported SSE mainboard issuer risk state required')
        _document(state['source_file'],state['source_sha256'])
        first,last,published=map(_day,(state['effective_from'],state['effective_through'],state['published_on']))
        available=parse_time(state['engineering_available_at']).astimezone(SHANGHAI)
        if (not start<=first<=last<=end or published>=first
                or available.date()<=published or available.date()>last):
            raise ValueError('explicit conservative source publication/effective/availability clock required')
        grouped.setdefault(state['instrument'],[]).append((first,last,state))
    for spans in grouped.values():
        spans.sort(key=lambda x:x[0])
        if any(b[0]<=a[1] for a,b in zip(spans,spans[1:])):
            raise ValueError('risk state intervals must be unique and nonoverlapping')
    active={c:state for c,spans in grouped.items() for first,last,state in spans if first<=day<=last}
    return at,active


def phase_market_view(row,phase):
    """Only phase-visible original values; never evaluate future-field values."""
    if phase not in PHASE_FIELDS or not isinstance(row,dict):
        raise ValueError('explicit PREOPEN/OPEN/CLOSE source phase required')
    if not {'date','tradestatus','isST'}<=set(row):raise ValueError('explicit market date/status fields required')
    return {key:row[key] for key in PHASE_FIELDS[phase] if key in row}


def regime_source_rows_on(bars,day,required,lifecycles,*,evidence,as_of):
    at,active=_validate_evidence(evidence,day,as_of);required=set(required)
    if any(c not in bars for c in active):raise ValueError('state proof issuer outside source universe')
    rows,exceptions=source_rows_on(bars,day,required,lifecycles);accepted={};regimes={}
    for code,row in rows.items():
        state=row.get('isST')
        if type(state) is not str or state not in ('0','1'):
            raise ValueError('explicit raw ordinary/risk-warning source state required')
        if 'code' in row and row['code']!=code[:2].lower()+'.'+code[2:]:
            raise ValueError('source row and regime security disagree')
        proof=active.get(code)
        if state=='0':
            if proof is not None:raise ValueError('ordinary source row conflicts with effective risk-warning proof')
            accepted[code]=row;regimes[code]={'kind':'ORDINARY_DAILY_OPEN_PROXY','instrument':code,
                'source_isST':'0','statutory_band_verified':False};continue
        visible=proof is not None and parse_time(proof['engineering_available_at'])<=at
        if not visible:
            if code in required:raise ValueError('required risk-warning source has no applicable visible proof: '+code+' '+day.isoformat())
            exceptions.append({'instrument':code,'session':day.isoformat(),
                'reason':'UNPROVEN_RISK_WARNING_SOURCE_NOT_REQUIRED','original_row_present':True,'source_isST':'1',
                'required_by_account':False,'synthetic_price_created':False});continue
        accepted[code]=row
        regimes[code]={'kind':'SSE_MAINBOARD_RISK_WARNING','instrument':code,'source_isST':'1',
            'as_of':iso(at),'state_interval_sha256':digest(proof),'evidence':deepcopy(evidence),
            'historical_arrival_verified':False}
    return accepted,exceptions,regimes


def risk_warning_limits(reference):
    ref=money(reference)
    if ref<CENT or ref!=ref.quantize(CENT):raise ValueError('positive cent-tick reference required')
    upper=(ref*Decimal('1.05')).quantize(CENT,rounding=ROUND_HALF_UP)
    lower=(ref*Decimal('.95')).quantize(CENT,rounding=ROUND_HALF_UP)
    if upper-ref<CENT:upper=ref+CENT
    if ref-lower<CENT:lower=ref-CENT
    lower=max(CENT,lower)
    return upper,lower


def execute_regime_open(broker,day,day_rows,regimes,*,validate_only=False):
    """Validate all pending-source bars before mutation, then use the old Broker.

    Permission/cap failures are explicit terminal order rejections, not source
    exceptions or fictional suspensions. The cap conservatively counts existing
    same-day BUY fills plus this batch's eligible requested BUY quantities.
    """
    if type(day) is not date or type(validate_only) is not bool or day not in broker.calendar.days:
        raise ValueError('explicit exchange session and validation mode required')
    at=broker.calendar.at(day,'09:30:00')
    pending=[o for o in broker.orders if o['status']=='PENDING']
    if not pending:return []
    codes=sorted({o['security_id'] for o in pending});bars=[];audit=[];planned=[];risk_caps={}
    for code in codes:
        if code not in day_rows or code not in regimes:raise ValueError('pending order source/regime missing')
        quote=phase_market_view(day_rows[code],'OPEN');regime=regimes[code]
        if (quote['date']!=day.isoformat() or quote['tradestatus'] not in ('0','1')
                or regime['instrument']!=code or quote['isST']!=regime['source_isST']
                or 'code' in quote and quote['code']!=code[:2].lower()+'.'+code[2:]):
            raise ValueError('execution source date/security/state mismatch')
        suspended=quote['tradestatus']=='0';item={'security_id':code,'trade_date':day.isoformat(),'suspended':suspended}
        upper=lower=None;risk=regime['kind']=='SSE_MAINBOARD_RISK_WARNING';permission=True
        if risk:
            when,active=_validate_evidence(regime['evidence'],day,regime['as_of']);proof=active.get(code)
            if (quote['isST']!='1' or proof is None or parse_time(proof['engineering_available_at'])>when
                    or when>at or regime['state_interval_sha256']!=digest(proof)
                    or regime.get('historical_arrival_verified') is not False):
                raise ValueError('opening risk regime proof is missing, late or mismatched')
            upper,lower=risk_warning_limits(quote.get('preclose'))
            permission=regime['evidence']['account_capabilities']['risk_warning_buy_permission']
        elif (regime['kind']!='ORDINARY_DAILY_OPEN_PROXY' or quote['isST']!='0'
                or regime.get('statutory_band_verified') is not False):
            raise ValueError('unknown execution regime')
        if not suspended:
            price=money(quote.get('open'))
            if price<=0 or price!=price.quantize(CENT):raise ValueError('actual opening price must lie on cent tick')
            if risk:
                if not lower<=price<=upper:raise ValueError('risk-warning open outside legal five-percent bands')
            else:
                ref=money(quote.get('preclose'));upper=ref*Decimal('1.095');lower=ref*Decimal('.905')
            item.update(open=str(price),limit_up=str(upper),limit_down=str(lower))
        # The unchanged validation method is read-only; do it for the entire
        # batch before annotating or rejecting even the first pending order.
        broker._validate_bar(item);bars.append(item)
        detail={'instrument':code,'phase':'OPEN','regime':regime['kind'],'quote':quote,
            'limit_up':str(upper) if upper is not None else None,'limit_down':str(lower) if lower is not None else None,
            'validate_only':validate_only,'orders':[]}
        if risk:
            used=0
            for fill in broker.fills:
                if fill['security_id']==code and fill['action']=='BUY' and parse_time(fill['execution_at']).astimezone(SHANGHAI).date()==day:
                    if type(fill['quantity']) is not int or fill['quantity']<=0:raise ValueError('invalid existing daily buy fill quantity')
                    used+=fill['quantity']
            risk_caps[code]=used
        for order in [o for o in pending if o['security_id']==code]:
            due=(parse_time(order['eligible_at'])==at and (not order.get('expires_at') or at<=parse_time(order['expires_at'])))
            due=due and (code,day) not in broker._processed
            status='DELEGATE_TO_EXISTING_BROKER';annotation=None
            if risk and due:
                if type(order['quantity']) is not int or order['quantity']<=0 or order['action'] not in ('BUY','SELL'):
                    raise ValueError('positive integer risk-warning order required')
                annotation={'order_type':'LIMIT','limit_price':str(upper if order['action']=='BUY' else lower),
                            'trading_regime_contract':CONTRACT}
                if order['action']=='BUY':
                    if not permission:status='UNFILLED_RISK_WARNING_PERMISSION'
                    elif risk_caps[code]+order['quantity']>500000:status='UNFILLED_RISK_WARNING_BUY_CAP'
                    else:risk_caps[code]+=order['quantity']
                planned.append((order,annotation,status))
            detail['orders'].append({'order_id':order['order_id'],'quantity':order['quantity'],
                'action':order['action'],'planned_status':status,**(annotation or {})})
        audit.append(detail)
    if validate_only:return audit
    for order,annotation,status in planned:
        order.update(annotation)
        if status!='DELEGATE_TO_EXISTING_BROKER':order['status']=status
    broker.on_market_open(bars)
    final={o['order_id']:o['status'] for o in broker.orders}
    for item in audit:
        for order in item['orders']:order['final_status']=final[order['order_id']]
    return audit
