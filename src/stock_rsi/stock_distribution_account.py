"""Separately versioned stock-dividend account under a flat tax stress reserve.

Taxable bonus shares are not tax-exempt capital transfers. This is not FIFO
tax settlement; events whose reserve exceeds cash fail without mutation.
The original RawShareAccount remains unchanged for frozen experiments.
"""
from dataclasses import dataclass
from decimal import Decimal,ROUND_HALF_UP
from stock_rsi.raw_share_account import CENT,Distribution,RawShareAccount


@dataclass(frozen=True)
class StockDistribution(Distribution):
    stock_per_share:Decimal=Decimal(0)
    stock_taxable_income_per_share:Decimal=Decimal(0)
    stock_tax_basis_verified:bool=False


class StockDistributionAccount(RawShareAccount):
    def __init__(self,calendar,initial_cash,distributions=(),**kwargs):
        events=tuple(distributions)
        for event in events:
            stock=getattr(event,'stock_per_share',Decimal(0))
            income=getattr(event,'stock_taxable_income_per_share',Decimal(0))
            if (not stock.is_finite() or not income.is_finite() or min(stock,income)<0
                    or stock>0 and (event.listed is None or event.listed<event.ex_date)
                    or stock==0 and income!=0):
                raise ValueError('invalid stock dividend amount, tax basis or listing time')
        super().__init__(calendar,initial_cash,events,**kwargs)

    def start_day(self,day):
        if not self._check_clock(day,0):return
        actions=[]
        for event in self.events:
            if event.ex_date!=day:continue
            if event.event_id not in self.entitlements and event.recorded>=self.calendar.days[0]:
                raise ValueError('record-date ownership was not observed')
            quantity=self.entitlements.get(event.event_id,0)
            if type(quantity) is not int or quantity<0:raise ValueError('invalid registered integer inventory')
            stock=getattr(event,'stock_per_share',Decimal(0))
            income=getattr(event,'stock_taxable_income_per_share',Decimal(0))
            if quantity and event.capital_per_share>0 and event.capital_tax_exempt_verified is not True:
                raise ValueError('applicable capital transfer tax treatment is unverified')
            if quantity and stock>0 and (getattr(event,'stock_tax_basis_verified',False) is not True or income<=0):
                raise ValueError('applicable stock dividend tax basis is unverified')
            capital_shares=event.capital_per_share*quantity;stock_shares=stock*quantity
            if any(v!=v.to_integral_value() for v in (capital_shares,stock_shares)):
                raise ValueError('fractional corporate entitlement needs registry allocation evidence')
            gross=(event.cash_per_share*quantity).quantize(CENT,rounding=ROUND_HALF_UP)
            stock_income=(income*quantity).quantize(CENT,rounding=ROUND_HALF_UP)
            reserve=((gross+stock_income)*self.tax_reserve_rate).quantize(CENT,rounding=ROUND_HALF_UP)
            if reserve>gross:
                raise ValueError('stock tax stress exceeds cash distribution; liability settlement unsupported')
            actions.append((event,quantity,int(capital_shares),int(stock_shares),gross,stock_income,reserve))
        # All event prerequisites are checked before any due payment or credit.
        for claim in self.cash_claims:
            if not claim['paid'] and claim['available_on']==day:
                self.broker.cash+=claim['net'];claim['paid']=True
                self.corporate_ledger.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE',
                    'event_id':claim['event_id'],'cash_delta':claim['net']})
        for event,quantity,capital,stock,gross,income,reserve in actions:
            if gross:
                available=next((at for at in self.calendar.days if at>event.pay_date),None)
                self.cash_claims.append({'event_id':event.event_id,'instrument':event.instrument,
                    'gross':gross,'reserve':reserve,'net':gross-reserve,'available_on':available,'paid':False})
            for amount,kind in ((capital,'CAPITAL_TRANSFER'),(stock,'STOCK_DIVIDEND')):
                if amount:
                    self.stock_claims.append({'event_id':event.event_id,'instrument':event.instrument,
                        'quantity':amount,'listed':event.listed,'recorded':event.recorded,
                        'credited':False,'share_kind':kind})
            self.corporate_ledger.append({'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':event.event_id,
                'instrument':event.instrument,'registered_quantity':quantity,'cash_gross':gross,
                'stress_tax_reserve':reserve,'capital_shares':capital,'stock_shares':stock,'taxable_stock_income':income})
        for claim in self.stock_claims:
            if not claim['credited'] and claim['listed']<=day:
                self.broker.positions.setdefault(claim['instrument'],[]).append({
                    'quantity':claim['quantity'],'bought_on':claim['recorded'],'price':Decimal(0)})
                claim['credited']=True
                self.corporate_ledger.append({'day':day,
                    'kind':'STOCK_DIVIDEND_SHARES_LISTED' if claim['share_kind']=='STOCK_DIVIDEND' else 'CAPITAL_SHARES_LISTED',
                    'event_id':claim['event_id'],'quantity':claim['quantity']})
        self._finish(day,0)
