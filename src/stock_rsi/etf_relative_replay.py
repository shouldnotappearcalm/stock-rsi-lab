"""Fixed three-ETF relative12m policy and physical daily-open proxy.

Current-vintage observations with reconstructed close arrival; no quote queue,
PIT completeness, broker commission schedule or official limit stream claim.
The signal reinvests distributions theoretically; the account does not.
"""
from decimal import Decimal as D,ROUND_HALF_UP
from fractions import Fraction
from stock_rsi.broker import money
from stock_rsi.data import Snapshot,canonical,digest
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import RawShareAccount,plan_integer_targets
from stock_rsi.time import iso

CODES=('SH510300','SH510500','SZ159915')
TICK=D('.001')

class ETFAccount(RawShareAccount):
    """Personal fund income exempt; payment available next explicit session.

    Pay-date intraday availability is not evidenced; next-session use is a
    declared conservative timing assumption, inherited without changing stocks.
    """
    def __init__(self,calendar,initial_cash,events=(),*,extra_cost_bps):
        events=tuple(events)
        if any(e.instrument not in CODES or e.capital_per_share!=0 or e.cash_per_share<=0 for e in events):
            raise ValueError('only verified cash distributions for fixed ETFs supported')
        def factory(cal,cash,**kwargs):
            return ExecutionCostBroker(cal,cash,extra_cost_bps=extra_cost_bps,buy_cost_bps='5',sell_cost_bps='5',min_cost='5')
        super().__init__(calendar,initial_cash,events,tax_reserve_rate='0',broker_factory=factory)

class Relative12Month:
    """Advances one close at a time. No future prices exist in this object."""
    def __init__(self,calendar):
        self.calendar=calendar;self.position=0;self.last={};self.index={c:Fraction(1) for c in CODES};self.monthends=[]
    def observe_close(self,day,closes,cashflows):
        if self.position>=len(self.calendar.days) or day!=self.calendar.days[self.position]:
            raise ValueError('all explicit closes must advance once in calendar order')
        if set(closes)!=set(CODES) or not set(cashflows)<=set(CODES):raise ValueError('all three visible ETFs required')
        closes={c:money(v) for c,v in closes.items()};cashflows={c:money(v) for c,v in cashflows.items()}
        if any(v<=0 for v in closes.values()) or any(v<0 for v in cashflows.values()):raise ValueError('positive closes/nonnegative cash required')
        if not self.last and cashflows:raise ValueError('cash ex-date requires prior close')
        for c in CODES:
            if self.last:self.index[c]*=Fraction(closes[c]+cashflows.get(c,D(0)))/Fraction(self.last[c])
        self.last=closes;self.position+=1
        following=self.calendar.days[self.position] if self.position<len(self.calendar.days) else None
        if following is not None and (following.year,following.month)==(day.year,day.month):return None
        self.monthends.append((day,self.index.copy()))
        if len(self.monthends)<13:return None
        window=self.monthends[-13:]
        ordinals=[d.year*12+d.month for d,_ in window]
        if any(b-a!=1 for a,b in zip(ordinals,ordinals[1:])):raise ValueError('13 consecutive complete months required')
        scores={c:self.index[c]/window[0][1][c]-1 for c in CODES}
        leader=sorted(CODES,key=lambda c:(-scores[c],c))[0]
        render=lambda v:str(D(v.numerator)/D(v.denominator))
        return {'as_of':day.isoformat(),'leader':leader,'scores':{c:render(scores[c]) for c in CODES},
                'scores_exact_ratio':{c:[str(scores[c].numerator),str(scores[c].denominator)] for c in CODES},
                'window_monthends':[d.isoformat() for d,_ in window],
                'total_return_index_monthends':[{c:render(v[c]) for c in CODES} for _,v in window]}

def execution_bar(day,code,previous_close,row,ex_cash):
    if code not in CODES:raise ValueError('fixed ETF execution universe required')
    price,volume=money(row['open']),money(row['volume_provider_raw'])
    if min(price,volume)<=0 or price!=price.quantize(TICK):
        raise ValueError('positive raw tick prices and observed daily volume required')
    ref=money(previous_close)-money(ex_cash)
    if ref<=0 or money(ex_cash)<0 or ref!=ref.quantize(TICK):raise ValueError('known positive ex-cash reference required')
    rate=D('.2') if code=='SZ159915' else D('.1')
    upper=(ref*(1+rate)).quantize(TICK,rounding=ROUND_HALF_UP);lower=(ref*(1-rate)).quantize(TICK,rounding=ROUND_HALF_UP)
    if not lower<=price<=upper:raise ValueError('opening price contradicts assumed historical price band')
    return {'security_id':code,'trade_date':day.isoformat(),'suspended':False,'open':str(price),
            'limit_up':str(upper),'limit_down':str(lower)}

def replay(calendar,bars,events,*,extra_cost_bps,initial_cash='1000000'):
    events=tuple(events);account=ETFAccount(calendar,initial_cash,events,extra_cost_bps=extra_cost_bps)
    signal=Relative12Month(calendar);prior={};rows=[];intents=[];prior_cash=money(initial_cash);prior_owned={};prior_equity=money(initial_cash)
    deferred=None;funding_intents=[]
    for number,day in enumerate(calendar.days):
        if day.isoformat() not in bars or set(bars[day.isoformat()])!=set(CODES):raise ValueError('complete fixed-universe daily bars required')
        today=bars[day.isoformat()]
        if any(r['date']!=day.isoformat() for r in today.values()):raise ValueError('bar date mismatch')
        closes={c:money(today[c]['close']) for c in CODES}
        at_ex=[e for e in events if e.ex_date==day]
        if any(e.announced>=day for e in at_ex):raise ValueError('ex cash was not publicly announced')
        if len({e.instrument for e in at_ex})!=len(at_ex):raise ValueError('ambiguous duplicate ex event')
        cashflows={e.instrument:e.cash_per_share for e in at_ex}
        before_corp=len(account.corporate_ledger);before_fills=len(account.broker.fills)
        account.start_day(day)
        pending={o['security_id'] for o in account.broker.orders if o['status']=='PENDING'}
        if pending:account.broker.on_market_open([execution_bar(day,c,prior[c],today[c],cashflows.get(c,D(0))) for c in sorted(pending)])
        account.end_day(day);wealth=account.wealth(closes);owned=account.owned_quantities()
        fills=account.broker.fills[before_fills:];corp=account.corporate_ledger[before_corp:]
        signed=sum((money(f['price'])*f['quantity']*(1 if f['action']=='BUY' else -1) for f in fills),D(0))
        fees=sum((money(f['cost']) for f in fills),D(0));paid=sum((r['cash_delta'] for r in corp if r['kind']=='NET_DIVIDEND_CASH_AVAILABLE'),D(0))
        if wealth['cash']!=prior_cash-signed-fees+paid:raise ValueError('cash reconciliation failed')
        expected=dict(prior_owned)
        for f in fills:expected[f['security_id']]=expected.get(f['security_id'],0)+f['quantity']*(1 if f['action']=='BUY' else -1)
        if {c:q for c,q in expected.items() if q}!=owned:raise ValueError('ETF integer unit reconciliation failed')
        if wealth['equity']!=wealth['cash']+wealth['cash_receivable']+sum((q*closes[c] for c,q in owned.items()),D(0)):
            raise ValueError('raw mark and receivable equity reconciliation failed')
        if day.year>=2024:
            rows.append({'day':day.isoformat(),'cash':wealth['cash'],'market_value':wealth['market_value'],
                'cash_receivable':wealth['cash_receivable'],'equity':wealth['equity'],'positions':owned.copy(),
                'marks':closes.copy(),'fees':fees,'dividend_cash_available':paid,'net_return':wealth['equity']/prior_equity-1,
                'exposure':wealth['market_value']/wealth['equity']})
        following=calendar.days[number+1] if number+1<len(calendar.days) else None
        # A monthly rotation never funds a buy from the same opening's sells.
        # Original quantities remain frozen; only the confirmation controls release.
        if deferred is not None and deferred['execution_session']==day.isoformat():
            sell_states={o['order_id']:o['status'] for o in account.broker.orders if o['order_id'] in deferred['sell_order_ids']}
            receipt={'formation_as_of':deferred['formation_as_of'],'original_formation_snapshot_sha256':deferred['snapshot_sha256'],
                'original_formation_quantity':deferred['buy_decisions'][0].quantity,'sell_order_statuses':sell_states,
                'original_score_record':deferred['record'],'confirmation_session':day.isoformat(),'decisions':[]}
            if set(sell_states)!=set(deferred['sell_order_ids']) or not all(v=='FILLED' for v in sell_states.values()):receipt['status']='CANCELLED_SELL_NOT_FULLY_FILLED'
            elif following is None:receipt['status']='CANCELLED_CALENDAR_END'
            else:
                asof=calendar.at(day,'15:05:00')
                confirmation={'record_id':digest({'day':day.isoformat(),'sell_states':sell_states,'fills':fills}),
                    'kind':'observed_sale_confirmation','available_at':iso(asof),'payload':{'sell_states':sell_states,'fills':fills}}
                snapshot=Snapshot(canonical({'as_of':iso(asof),'records':[deferred['record'],confirmation],
                    'account':{'equity':str(wealth['equity']),'cash':str(wealth['cash']),'positions':owned}}))
                buys=[Decision.from_dict({'action':d.action,'security_id':d.security_id,'quantity':d.quantity,
                    'evidence_ids':[deferred['record']['record_id'],confirmation['record_id']],
                    'reason':'release original fixed monthly buy only after observed full sale; next-session execution'},snapshot)
                    for d in deferred['buy_decisions']]
                account.broker.replace_pending_intent(buys,asof,calendar.at(following,'09:30:00'))
                receipt.update(status='CONFIRMED_SALE_THEN_NEXT_SESSION_BUY',submitted_at=iso(asof),
                    execution_session=following.isoformat(),snapshot_sha256=snapshot.sha256,decisions=[d.to_dict() for d in buys])
            funding_intents.append(receipt);deferred=None
        formation=signal.observe_close(day,closes,cashflows)
        if formation and following and following.year>=2024:
            orders=plan_integer_targets(wealth['equity'],owned,{formation['leader']:'.95'},closes)
            asof=calendar.at(day,'15:05:00');record={'record_id':digest(formation),'kind':'visible_monthly_ETF_total_returns',
                'available_at':iso(asof),'payload':formation}
            snapshot=Snapshot(canonical({'as_of':iso(asof),'records':[record],'account':{'equity':str(wealth['equity']),
              'cash':str(wealth['cash']),'cash_receivable':str(wealth['cash_receivable']),'positions':owned,'raw_close':{c:str(v) for c,v in closes.items()}}}))
            decisions=[Decision.from_dict({'action':a,'security_id':c,'quantity':q,'evidence_ids':[record['record_id']],
                'reason':'fixed three domestic ETF relative12m, prior-close 95% target'},snapshot) for a,c,q in orders]
            sells=[d for d in decisions if d.action=='SELL'];buys=[d for d in decisions if d.action=='BUY']
            if sells and buys:
                if deferred is not None or len(buys)!=1:raise ValueError('ambiguous staged monthly intent')
                submitted=account.broker.replace_pending_intent(sells,asof,calendar.at(following,'09:30:00'))
                deferred={'execution_session':following.isoformat(),'formation_as_of':iso(asof),'buy_decisions':buys,
                    'sell_order_ids':[o['order_id'] for o in submitted],'snapshot_sha256':snapshot.sha256,'record':record}
            else:account.broker.replace_pending_intent(decisions,asof,calendar.at(following,'09:30:00'))
            intents.append({'execution_session':following.isoformat(),'as_of':iso(asof),'formation':formation,
                'equity_at_decision':wealth['equity'],'owned_integer_units':owned.copy(),'raw_close':closes.copy(),
                'snapshot_sha256':snapshot.sha256,'decisions':[d.to_dict() for d in decisions]})
        prior,prior_cash,prior_owned,prior_equity=closes,wealth['cash'],owned.copy(),wealth['equity']
    return {'days':rows,'intents':intents,'fills':account.broker.fills,'orders':account.broker.orders,'funding_intents':funding_intents,
        'corporate_ledger':account.corporate_ledger,'ledger_checks':'ALL_SESSIONS_CASH_UNITS_EQUITY_RECONCILED',
        'evidence_level':'CURRENT_VINTAGE_REAL_PRICE_DAILY_OPEN_ENGINEERING_PROXY','historical_arrival_certified':False,
        'opening_fill_or_queue_certified':False,'official_historical_limit_stream_certified':False,
        'primary_action_completeness_certified':False,'candidate_promoted':False,'objective_achieved':False}
