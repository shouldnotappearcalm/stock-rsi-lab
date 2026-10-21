"""Two frozen SSE mainboard risk-warning epochs, separate from old evaluation.

Metadata only: caller authenticates original document bytes. Conservative
availability is not actual arrival. No strategy, quantity, account or tax change.
Only explicit ordinary/risk-warning source rows within this contract are used.
"""
from copy import deepcopy
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
import re

from stock_rsi.broker import money
from stock_rsi.calendar import SHANGHAI
from stock_rsi.data import digest
from stock_rsi.lifecycle_source_rows import source_rows_on
from stock_rsi.time import iso, parse_time
from stock_rsi.trading_regime_source import _day, _document, STATE_FIELDS, phase_market_view

CONTRACT='SSE_MAINBOARD_RISK_WARNING_HORIZON_V1'
CENT=Decimal('.01')
START=date(2023,12,29)
END=date(2026,10,20)
EPOCH_FIELDS={'source_file','sha256','published_on','engineering_available_at',
              'actual_arrival_verified','valid_from','valid_through','limit_ratio'}
EPOCHS=(('2023-12-29','2026-07-05','0.05'),('2026-07-06','2026-10-20','0.10'))


def validate_regime_evidence(evidence,day,as_of):
    """Return copied validated active metadata; no file reads or market values."""
    if (not isinstance(evidence,dict) or set(evidence)!={'contract','rule_epochs','state_intervals','account_capabilities'}
            or evidence['contract']!=CONTRACT or type(day) is not date or not START<=day<=END):
        raise ValueError('explicit SSE mainboard horizon contract and session required')
    at=parse_time(as_of)
    if at.astimezone(SHANGHAI).date()!=day:raise ValueError('as-of session mismatch')
    epochs=evidence['rule_epochs'];caps=evidence['account_capabilities']
    if not isinstance(epochs,list) or len(epochs)!=2:raise ValueError('exact two frozen SSE rule epochs required')
    for index,(rule,expected) in enumerate(zip(epochs,EPOCHS)):
        if (not isinstance(rule,dict) or set(rule)!=EPOCH_FIELDS
                or tuple(rule[k] for k in ('valid_from','valid_through','limit_ratio'))!=expected
                or rule['actual_arrival_verified'] is not False):
            raise ValueError('fixed source rule epoch, ratio and unverified actual arrival required')
        _document(rule['source_file'],rule['sha256'])
        first,last,published=map(_day,(rule['valid_from'],rule['valid_through'],rule['published_on']))
        available=parse_time(rule['engineering_available_at']).astimezone(SHANGHAI)
        if (published>=first or available.date()<=published
                or available>datetime.combine(first,time.min,tzinfo=SHANGHAI)
                or index==1 and rule['published_on']!='2026-04-24'):
            raise ValueError('rule publication or conservative engineering availability invalid')
    if (epochs[0]['source_file']==epochs[1]['source_file'] or epochs[0]['sha256']==epochs[1]['sha256']):
        raise ValueError('separately bound original 2023 and 2026 rule documents required')
    if (not isinstance(caps,dict) or set(caps)!={'risk_warning_buy_permission'}
            or type(caps['risk_warning_buy_permission']) is not bool):
        raise ValueError('explicit boolean account permission required')
    selected=next(rule for rule in epochs if _day(rule['valid_from'])<=day<=_day(rule['valid_through']))
    if parse_time(selected['engineering_available_at'])>at:raise ValueError('selected rule not available as of session')
    intervals=evidence['state_intervals']
    if not isinstance(intervals,list):raise ValueError('explicit source intervals required')
    grouped={}
    for state in intervals:
        if (not isinstance(state,dict) or set(state)!=STATE_FIELDS
                or not isinstance(state['instrument'],str)
                or not re.fullmatch(r'SH(?:600|601|603|605)[0-9]{3}',state['instrument'])
                or state['exchange']!='SSE' or state['board']!='MAINBOARD'
                or state['risk_status'] not in ('OTHER_RISK_WARNING','DELISTING_RISK_WARNING')
                or state['actual_arrival_verified'] is not False):
            raise ValueError('supported SSE mainboard source risk state required')
        _document(state['source_file'],state['source_sha256'])
        first,last,published=map(_day,(state['effective_from'],state['effective_through'],state['published_on']))
        available=parse_time(state['engineering_available_at']).astimezone(SHANGHAI)
        if not START<=first<=last<=END or published>=first or available.date()<=published or available.date()>last:
            raise ValueError('explicit conservative issuer publication/effective/availability clock required')
        grouped.setdefault(state['instrument'],[]).append((first,last,state))
    for spans in grouped.values():
        spans.sort(key=lambda x:x[0])
        if any(b[0]<=a[1] for a,b in zip(spans,spans[1:])):
            raise ValueError('issuer state intervals globally unique and nonoverlapping required')
    active={c:state for c,spans in grouped.items() for first,last,state in spans if first<=day<=last}
    return {'as_of':iso(at),'rule_epoch':deepcopy(selected),'active_states':deepcopy(active)}


def regime_source_rows_on(bars,day,required,lifecycles,*,evidence,as_of):
    validated=validate_regime_evidence(evidence,day,as_of)
    at=parse_time(validated['as_of']);active=validated['active_states'];required=set(required)
    # Evidence covers the globally authenticated universe; a causal source
    # view may omit not-yet-visible, unrequired issuers. Required omissions
    # still fail in the unchanged lifecycle source helper.
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
                'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1',
                'required_by_account':False,'synthetic_price_created':False});continue
        accepted[code]=row
        regimes[code]={'kind':'SSE_MAINBOARD_RISK_WARNING','instrument':code,'source_isST':'1',
            'as_of':iso(at),'state_interval_sha256':digest(proof),
            'rule_epoch_sha256':digest(validated['rule_epoch']),'rule_epoch':deepcopy(validated['rule_epoch']),
            'evidence':deepcopy(evidence),
            'historical_arrival_verified':False}
    return accepted,exceptions,regimes


def risk_warning_limits(reference,limit_ratio='0.05'):
    if type(limit_ratio) is not str or limit_ratio not in ('0.05','0.10'):
        raise ValueError('only frozen five/ten percent rule ratios supported')
    ratio=Decimal(limit_ratio)
    ref=money(reference)
    if ref<CENT or ref!=ref.quantize(CENT):raise ValueError('positive cent-tick reference required')
    upper=(ref*(Decimal(1)+ratio)).quantize(CENT,rounding=ROUND_HALF_UP)
    lower=(ref*(Decimal(1)-ratio)).quantize(CENT,rounding=ROUND_HALF_UP)
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
            validated=validate_regime_evidence(regime['evidence'],day,regime['as_of'])
            when=parse_time(validated['as_of']);proof=validated['active_states'].get(code)
            epoch=validated['rule_epoch']
            if (quote['isST']!='1' or proof is None or parse_time(proof['engineering_available_at'])>when
                    or when>at or regime['state_interval_sha256']!=digest(proof)
                    or regime.get('historical_arrival_verified') is not False
                    or regime.get('rule_epoch_sha256')!=digest(epoch) or regime.get('rule_epoch')!=epoch):
                raise ValueError('opening risk regime proof is missing, late or mismatched')
            upper,lower=risk_warning_limits(quote.get('preclose'),epoch['limit_ratio'])
            permission=regime['evidence']['account_capabilities']['risk_warning_buy_permission']
        elif (regime['kind']!='ORDINARY_DAILY_OPEN_PROXY' or quote['isST']!='0'
                or regime.get('statutory_band_verified') is not False):
            raise ValueError('unknown execution regime')
        if not suspended:
            price=money(quote.get('open'))
            if price<=0 or price!=price.quantize(CENT):raise ValueError('actual opening price must lie on cent tick')
            if risk:
                if not lower<=price<=upper:raise ValueError('risk-warning open outside selected legal epoch bands')
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
