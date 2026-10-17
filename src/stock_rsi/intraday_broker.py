"""Nested five-minute sampled-price execution for fixed daily parent intents.

This is a declared participation/cost scenario, not a queue or impact model.
Parent instructions and actual exchange-sized children are recorded separately.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP

from stock_rsi.broker import money
from stock_rsi.calendar import SHANGHAI
from stock_rsi.data import digest
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.models import Decision
from stock_rsi.time import iso, parse_time


class IntradayBroker(ExecutionCostBroker):
    def __init__(self,calendar,initial_cash="100000",*,participation_bps=500,extra_cost_bps=0,tape_provider=None,**kwargs):
        if type(participation_bps) is not int or participation_bps not in (100,500,1000):
            raise ValueError("registered participation bps required")
        super().__init__(calendar,initial_cash,extra_cost_bps=extra_cost_bps,
                         **{"buy_cost_bps":"5","sell_cost_bps":"15","min_cost":"5",**kwargs})
        self.participation_bps=participation_bps;self.tape_provider=tape_provider
        self.child_orders=[];self._batches={};self._windows={};self._last_end=None;self._drained_days=set()

    @staticmethod
    def _parent_valid(decision):
        if not isinstance(decision,Decision) or type(decision.quantity) is not int:
            raise ValueError("typed integer parent instruction required")
        if decision.action in ("BUY","SELL"):
            if decision.quantity<=0 or decision.action=="BUY" and decision.quantity%100:
                raise ValueError("positive parent quantity and 100-share buys required")
        elif decision.action not in ("HOLD","ABSTAIN") or decision.quantity!=0:
            raise ValueError("invalid parent action/quantity")

    def replace_pending_intent(self,decisions,at,expires_at):
        if not isinstance(decisions,(list,tuple)):raise ValueError("parent batch required")
        for decision in decisions:self._parent_valid(decision)
        if len({d.security_id for d in decisions})!=len(decisions):raise ValueError("duplicate parent security")
        at=parse_time(at);hint=parse_time(expires_at);eligible=self.calendar.next_day_open(at)
        expiry=self.calendar.at(eligible.astimezone(SHANGHAI).date(),"14:55:00")
        if hint not in (eligible,expiry) or hint<=at:raise ValueError("invalid declared parent expiry hint")
        batch=digest({"decisions":[d.decision_id for d in decisions],"at":iso(at),"participation":self.participation_bps,"extra":str(self.extra_rate)})
        if batch in self._batches:return [p.copy() for p in self.orders if p['order_id'] in self._batches[batch]]
        if self._last_end is not None and at<self._last_end:raise ValueError("parent clock cannot move backward")
        new=[]
        for decision in decisions:
            if decision.action in ("HOLD","ABSTAIN"):continue
            key=digest({"batch":batch,"decision":decision.decision_id,"role":"intraday_parent"})
            new.append({"order_id":key,"decision_id":decision.decision_id,"security_id":decision.security_id,
                        "action":decision.action,"quantity":decision.quantity,"remaining":decision.quantity,
                        "filled_quantity":0,"submitted_at":iso(at),"eligible_at":iso(eligible),
                        "expires_at":iso(expiry),"legacy_expiry_hint":iso(hint),"status":"PENDING",
                        "order_role":"PARENT_EXECUTION_INSTRUCTION_NOT_EXCHANGE_ORDER"})
        for parent in self.orders:
            if parent['status']=='PENDING':parent['status']='CANCELLED_BY_PORTFOLIO_REPLACEMENT'
        self.orders.extend(new);self._batches[batch]=tuple(p['order_id'] for p in new)
        return [p.copy() for p in new]

    def submit(self,*args,**kwargs):
        raise ValueError("use an atomic portfolio parent batch")

    def on_open(self,bar):
        raise ValueError("use the complete nested on_market_open batch")

    def _parents(self,day):
        return [p for p in self.orders if p['status']=='PENDING' and parse_time(p['eligible_at']).astimezone(SHANGHAI).date()==day]

    def _window_clock(self,start,end):
        start,end=parse_time(start),parse_time(end);local_start,local_end=start.astimezone(SHANGHAI),end.astimezone(SHANGHAI)
        a,b=local_start.strftime('%H:%M:%S'),local_end.strftime('%H:%M:%S')
        if (local_start.date()!=local_end.date() or local_start.date() not in self.calendar.days
                or end-start!=timedelta(minutes=5) or local_start.minute%5 or local_start.second
                or not ('09:35:00'<=a<b<='11:30:00' or '13:00:00'<=a<b<='14:55:00')):
            raise ValueError("explicit continuous five-minute execution window required")
        return start,end,local_start.date()

    @staticmethod
    def _bar(value,code=None):
        if not isinstance(value,dict):raise ValueError("known execution bar required")
        if code is not None and value.get('security_id')!=code:raise ValueError("execution bar security mismatch")
        if not isinstance(value.get('evidence_id'),str) or not value['evidence_id']:
            raise ValueError("nonempty bucket evidence required")
        start,end=parse_time(value['start']),parse_time(value['end'])
        if end-start!=timedelta(minutes=5) or parse_time(value['available_at'])!=end:
            raise ValueError("invalid observed bucket clock")
        volume=value['volume_lower_shares']
        if type(volume) is not int or volume<0:raise ValueError("integer lower-volume bound required")
        buy,sell=value['buy_price'],value['sell_price']
        if buy is None or sell is None:
            if volume or buy is not None or sell is not None:raise ValueError("missing positive-volume prices")
            return volume,None,None
        buy,sell=money(buy),money(sell)
        if sell<=0 or sell>buy or buy!=buy.quantize(Decimal('.01')) or sell!=sell.quantize(Decimal('.01')):
            raise ValueError("positive cent sampled prices required")
        return volume,buy,sell

    @staticmethod
    def _reference(value):
        if not isinstance(value,dict) or type(value.get('suspended')) is not bool:raise ValueError("explicit market state required")
        if value['suspended']:return None,None,True
        upper=money(value['limit_up']).quantize(Decimal('.01'),rounding=ROUND_DOWN)
        lower=money(value['limit_down']).quantize(Decimal('.01'),rounding=ROUND_UP)
        if not 0<lower<upper:raise ValueError("positive protective prices required")
        return upper,lower,value['suspended']

    def _sellable(self,code,day):
        return sum(lot['quantity'] for lot in self.positions.get(code,[]) if lot['bought_on']<day)

    @staticmethod
    def _quantity(remaining,capacity,action):
        cap=min(remaining,capacity,1000000)
        if action=='SELL' and remaining<=cap:return remaining
        return cap//100*100

    def plan_window(self,start,end,previous,references):
        start,end,day=self._window_clock(start,end);budget=self.cash;children=[]
        expected_previous=start if start.astimezone(SHANGHAI).strftime('%H:%M')!='13:00' else self.calendar.at(day,'11:30:00')
        for parent in sorted(self._parents(day),key=lambda p:(p['action']!='SELL',p['security_id'])):
            code=parent['security_id'];bar=previous[code]
            volume,_,_=self._bar(bar,code);upper,lower,suspended=self._reference(references[code])
            if parse_time(bar['end'])!=expected_previous:raise ValueError("only immediately prior completed bucket may size a child")
            if suspended:continue
            capacity=volume*self.participation_bps//10000
            action=parent['action'];remaining=parent['remaining']
            if action=='SELL':capacity=min(capacity,self._sellable(code,day))
            quantity=self._quantity(remaining,capacity,action);limit=upper if action=='BUY' else lower
            if action=='BUY':
                quantity=min(quantity,int(budget/limit)//100*100)
                while quantity and limit*quantity+self._cost(limit*quantity,action)>budget:quantity-=100
            if not quantity:continue
            reserve=limit*quantity+self._cost(limit*quantity,action) if action=='BUY' else Decimal(0)
            if action=='BUY':budget-=reserve
            child_id=digest({'parent':parent['order_id'],'start':iso(start),'end':iso(end),'quantity':quantity,
                             'previous_volume':volume,'evidence_id':bar['evidence_id']})
            children.append({'order_id':child_id,'parent_id':parent['order_id'],'security_id':code,'action':action,
                'quantity':quantity,'limit_price':str(limit),'submitted_at':iso(start),'expires_at':iso(end),
                'status':'PENDING','filled_quantity':0,'order_role':'EXPLICIT_CHILD_ORDER','source_volume_as_of':iso(expected_previous),
                'source_volume_lower_shares':volume,'source_evidence_id':bar['evidence_id'],'reserved_cash':str(reserve)})
        return children

    def on_window(self,start,end,previous,current,references):
        start,end,day=self._window_clock(start,end)
        key=(iso(start),iso(end));fingerprint=digest({'previous':previous,'current':current,'references':references})
        if key in self._windows:
            if self._windows[key]!=fingerprint:raise ValueError("processed window data changed")
            return []
        if self._last_end is not None and start<self._last_end:raise ValueError("execution clock must advance")
        children=self.plan_window(start,end,previous,references)
        # Admit all current data before a parent, cash or inventory mutation.
        for parent in self._parents(day):
            row=current[parent['security_id']];self._bar(row,parent['security_id'])
            if parse_time(row['start'])!=start or parse_time(row['end'])!=end:raise ValueError("current bucket identity mismatch")
        new=[];parents={p['order_id']:p for p in self.orders}
        self.child_orders.extend(children)
        # All budgets were fixed before the interval. Buys cannot use its sales.
        for child in sorted(children,key=lambda c:(c['action']!='BUY',c['security_id'])):
            code=child['security_id'];action=child['action'];parent=parents[child['parent_id']]
            volume,buy,sell=self._bar(current[code],code);price=buy if action=='BUY' else sell
            capacity=volume*self.participation_bps//10000
            quantity=self._quantity(min(parent['remaining'],child['quantity']),capacity,action)
            if (not quantity or price is None or action=='BUY' and price>=money(child['limit_price'])
                    or action=='SELL' and price<=money(child['limit_price'])):
                child['status']='UNFILLED_VOLUME_OR_PRICE';continue
            if action=='SELL' and quantity>self._sellable(code,day):raise ValueError("sell exceeds T+1 inventory")
            gross=price*quantity;cost=self._cost(gross,action)
            if action=='BUY' and gross+cost>self.cash:raise ValueError("reserved buy cash failed")
            if action=='SELL' and self.cash+gross<cost:
                child['status']='UNFILLED_FEES_CASH';continue
            if action=='BUY':
                self.cash-=gross+cost
                self.positions.setdefault(code,[]).append({'quantity':quantity,'bought_on':day,'price':price})
            else:
                self.cash+=gross-cost;left=quantity
                for lot in self.positions.get(code,[]):
                    if lot['bought_on']>=day:continue
                    taken=min(left,lot['quantity']);lot['quantity']-=taken;left-=taken
                self.positions[code]=[lot for lot in self.positions[code] if lot['quantity']]
                if not self.positions[code]:self.positions.pop(code)
            parent['remaining']-=quantity;parent['filled_quantity']+=quantity
            if not parent['remaining']:parent['status']='FILLED'
            child['status']='FILLED' if quantity==child['quantity'] else 'PARTIAL_WINDOW_EXPIRED'
            child['filled_quantity']=quantity
            fill={'order_id':child['order_id'],'parent_id':parent['order_id'],'execution_at':iso(end),'security_id':code,
                  'action':action,'quantity':quantity,'price':str(price),'cost':str(cost),'cash_after':str(self.cash),
                  'current_volume_lower_shares':volume,'current_evidence_id':current[code]['evidence_id']}
            self.fills.append(fill);new.append(fill.copy())
        self._windows[key]=fingerprint;self._last_end=end
        return new

    def expire_day(self,day):
        for parent in self._parents(day):
            parent['status']='PARTIAL_DAY_EXPIRED' if parent['filled_quantity'] else 'UNFILLED_DAY_EXPIRED'
        expiry=self.calendar.at(day,'14:55:00')
        if self._last_end is None or expiry>self._last_end:self._last_end=expiry

    def on_market_open(self,bars):
        if not bars or self.tape_provider is None:raise ValueError("nested daily executor requires tape provider")
        days={bar['trade_date'] for bar in bars}
        if len(days)!=1 or len({b['security_id'] for b in bars})!=len(bars):raise ValueError("unique same-day market batch required")
        day=date.fromisoformat(next(iter(days)))
        if day in self._drained_days:return []
        parents=self._parents(day);required={p['security_id'] for p in parents};provided={b['security_id'] for b in bars}
        if provided!=required:raise ValueError("complete parent-day market state required")
        references={b['security_id']:{'limit_up':b.get('limit_up'),'limit_down':b.get('limit_down'),
                                     'suspended':b['suspended']} for b in bars}
        records={}
        for code in sorted(required):
            self._reference(references[code])
            if references[code]['suspended']:continue
            rows=self.tape_provider(code,day)
            if not isinstance(rows,list) or len(rows)!=48:raise ValueError("complete historical five-minute windows required")
            ends=[f'{hour:02d}:{minute:02d}:00' for hour in (9,10,11,13,14,15) for minute in range(0,60,5)
                  if '09:35'<=f'{hour:02d}:{minute:02d}'<='11:30' or '13:05'<=f'{hour:02d}:{minute:02d}'<='15:00']
            for row,clock in zip(rows,ends):
                self._bar(row,code)
                if parse_time(row['end'])!=self.calendar.at(day,clock):raise ValueError("whole-day bucket clock changed")
            records[code]=rows
        for parent in parents:
            if references[parent['security_id']]['suspended']:parent['status']='UNFILLED_HALTED_DAY'
        before=len(self.fills)
        for index in range(1,47):
            active=self._parents(day)
            if not active:break
            codes={p['security_id'] for p in active};current={code:records[code][index] for code in codes}
            previous={code:records[code][index-1] for code in codes}
            end=parse_time(next(iter(current.values()))['end']);start=end-timedelta(minutes=5)
            self.on_window(start,end,previous,current,{code:references[code] for code in codes})
        self.expire_day(day);self._drained_days.add(day)
        return [f.copy() for f in self.fills[before:]]
