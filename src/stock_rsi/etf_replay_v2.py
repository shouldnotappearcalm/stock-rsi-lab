"""Separately versioned ETF engine with an explicit close-only signal dependency.

Preserves the frozen first engine rather than changing its authenticated bytes.
Only factory/reason injection differ; original-policy behavior is regression-tested.
"""
from decimal import Decimal as D
from stock_rsi.broker import money
from stock_rsi.data import Snapshot,canonical,digest
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import plan_integer_targets
from stock_rsi.time import iso
from stock_rsi.etf_relative_replay import CODES,ETFAccount,execution_bar

PARENT_ENGINE_MODULE_SHA256='6b1662aa696e806c4eca62717aeeb3b74fa3edcf0943a7c34a9cf62e39b6deb7'

def replay_with_signal(calendar,bars,events,*,signal_factory,decision_reason,extra_cost_bps,initial_cash='1000000'):
    events=tuple(events);account=ETFAccount(calendar,initial_cash,events,extra_cost_bps=extra_cost_bps)
    signal=signal_factory(calendar);prior={};rows=[];intents=[];prior_cash=money(initial_cash);prior_owned={};prior_equity=money(initial_cash)
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
                'reason':decision_reason},snapshot) for a,c,q in orders]
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
