"""Counterfactual full-par capital-income reserve, never a tax exemption proof.

Original account and distribution flags stay unchanged. The registry is a
researcher-reviewed par-value extraction bound to original source bytes; it
is not an automatic interpretation of PDF text or confirmed tax liability.
"""
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from stock_rsi.raw_share_account import CENT
from stock_rsi.stock_distribution_account import StockDistributionAccount


def event_fingerprint(event):
    return hashlib.sha256(json.dumps(asdict(event), sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class CapitalIncomeBasis:
    event_id: str
    event_sha256: str
    par_value_CNY: Decimal
    source_sha256: tuple


def load_capital_income_basis(registry, source_root, events):
    """Authenticate reviewed extraction/units and event identity before replay."""
    if registry['status'] != 'COUNTERFACTUAL_PAR_VALUE_BASIS_NOT_TAX_EXEMPTION':
        raise ValueError('counterfactual basis registry required')
    root = Path(source_root).resolve(); by_id = {e.event_id:e for e in events}; result = {}
    for row in registry['events']:
        event = by_id.get(row['event_id'])
        if (event is None or row['event_id'] in result or event.capital_per_share <= 0
                or event.capital_tax_exempt_verified is not False
                or row['instrument'] != event.instrument or row['recorded'] != event.recorded.isoformat()
                or row['ex_date'] != event.ex_date.isoformat() or row['event_sha256'] != event_fingerprint(event)):
            raise ValueError('capital scenario event identity changed')
        capital = Decimal(row['nominal_capital_CNY']); par = Decimal(row['par_value_CNY']); shares = row['ordinary_shares']
        if (not capital.is_finite() or not par.is_finite() or min(capital, par) <= 0
                or type(shares) is not int or shares <= 0 or capital != shares*par or not row['issuer']):
            raise ValueError('positive consistent capital/share/par basis required')
        sources = row['sources']; roles = [s['role'] for s in sources]
        if sorted(roles) != ['nominal_capital', 'ordinary_shares']:
            raise ValueError('two independently bound capital and share source roles required')
        hashes = []
        for source in sources:
            path = root/source['file']; resolved = path.resolve()
            if (Path(source['file']).is_absolute() or '..' in Path(source['file']).parts
                    or not resolved.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']
                    or source['instrument'] != event.instrument or source['issuer'] != row['issuer']
                    or type(source['page']) is not int or source['page'] < 1
                    or date.fromisoformat(source['publication_day']) > event.announced):
                raise ValueError('capital par source bytes, issuer, page or publication changed')
            values = source['extracted']
            if source['role'] == 'nominal_capital':
                unit = Decimal(values['unit_multiplier']); amount = Decimal(values['nominal_capital'])
                if (values['currency'] != 'CNY' or not unit.is_finite() or not amount.is_finite()
                        or min(unit,amount) <= 0 or amount*unit != capital):
                    raise ValueError('nominal capital currency/unit extraction mismatch')
            elif values['unit'] != 'shares' or type(values['ordinary_shares']) is not int or values['ordinary_shares'] != shares:
                raise ValueError('ordinary share count/unit extraction mismatch')
            hashes.append((source['role'], source['sha256']))
        result[event.event_id] = CapitalIncomeBasis(event.event_id, event_fingerprint(event), par, tuple(sorted(hashes)))
    return MappingProxyType(result)


class CapitalIncomeStressAccount(StockDistributionAccount):
    def __init__(self, calendar, initial_cash, distributions=(), *, capital_income_basis, **kwargs):
        events = tuple(distributions)
        super().__init__(calendar, initial_cash, events, **kwargs)
        if self.tax_reserve_rate != Decimal('.2'):
            raise ValueError('capital-income scenario reserve must be fixed20percent')
        by_id = {e.event_id:e for e in events}
        for key, basis in capital_income_basis.items():
            if (not isinstance(basis, CapitalIncomeBasis) or key not in by_id or key != basis.event_id
                    or basis.event_sha256 != event_fingerprint(by_id[key]) or not basis.par_value_CNY.is_finite()
                    or basis.par_value_CNY <= 0):
                raise ValueError('capital scenario basis is unverified or bound to another event')
        self.capital_income_basis = MappingProxyType(dict(capital_income_basis))
        self.capital_stress_ledger = []

    def start_day(self, day):
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
            basis = self.capital_income_basis.get(event.event_id)
            capital_income = Decimal(0)
            if quantity and event.capital_per_share>0 and event.capital_tax_exempt_verified is not True:
                if basis is None:raise ValueError('applicable capital transfer tax treatment is unverified; no scenario par basis')
                capital_income = (event.capital_per_share*quantity*basis.par_value_CNY).quantize(CENT,rounding=ROUND_HALF_UP)
            if quantity and stock>0 and (getattr(event,'stock_tax_basis_verified',False) is not True or income<=0):
                raise ValueError('applicable stock dividend tax basis is unverified')
            capital_shares=event.capital_per_share*quantity;stock_shares=stock*quantity
            if any(v!=v.to_integral_value() for v in (capital_shares,stock_shares)):
                raise ValueError('fractional corporate entitlement needs registry allocation evidence')
            gross=(event.cash_per_share*quantity).quantize(CENT,rounding=ROUND_HALF_UP)
            stock_income=(income*quantity).quantize(CENT,rounding=ROUND_HALF_UP)
            reserve=((gross+stock_income+capital_income)*self.tax_reserve_rate).quantize(CENT,rounding=ROUND_HALF_UP)
            if reserve>gross:
                raise ValueError('stock/capital tax stress exceeds cash distribution; liability settlement unsupported')
            actions.append((event,quantity,int(capital_shares),int(stock_shares),gross,stock_income,reserve,capital_income,basis))
        # Validate the whole batch before paying a prior claim or crediting shares.
        for claim in self.cash_claims:
            if not claim['paid'] and claim['available_on']==day:
                self.broker.cash+=claim['net'];claim['paid']=True
                self.corporate_ledger.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE',
                    'event_id':claim['event_id'],'cash_delta':claim['net']})
        for event,quantity,capital,stock,gross,income,reserve,capital_income,basis in actions:
            if gross:
                available=next((at for at in self.calendar.days if at>event.pay_date),None)
                self.cash_claims.append({'event_id':event.event_id,'instrument':event.instrument,
                    'gross':gross,'reserve':reserve,'net':gross-reserve,'available_on':available,'paid':False})
            for amount,kind in ((capital,'CAPITAL_TRANSFER'),(stock,'STOCK_DIVIDEND')):
                if amount:
                    self.stock_claims.append({'event_id':event.event_id,'instrument':event.instrument,
                        'quantity':amount,'listed':event.listed,'recorded':event.recorded,
                        'credited':False,'share_kind':kind})
            entry={'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':event.event_id,
                'instrument':event.instrument,'registered_quantity':quantity,'cash_gross':gross,
                'stress_tax_reserve':reserve,'capital_shares':capital,'stock_shares':stock,'taxable_stock_income':income}
            if capital_income:
                baseline_reserve=((gross+income)*self.tax_reserve_rate).quantize(CENT,rounding=ROUND_HALF_UP)
                entry['taxable_capital_stress_income']=capital_income
                self.capital_stress_ledger.append({'day':day,'event_id':event.event_id,'registered_quantity':quantity,
                    'capital_shares':capital,'par_value_CNY':basis.par_value_CNY,'capital_income_CNY':capital_income,
                    'baseline_cash_and_stock_reserve_CNY':baseline_reserve,'additional_scenario_reserve_CNY':reserve-baseline_reserve,
                    'combined_reserve_CNY':reserve,'source_sha256':basis.source_sha256,
                    'capital_tax_exempt_verified':event.capital_tax_exempt_verified,
                    'status':'COUNTERFACTUAL_FULL_CAPITAL_INCOME_TAX_STRESS'})
            self.corporate_ledger.append(entry)
        for claim in self.stock_claims:
            if not claim['credited'] and claim['listed']<=day:
                self.broker.positions.setdefault(claim['instrument'],[]).append({
                    'quantity':claim['quantity'],'bought_on':claim['recorded'],'price':Decimal(0)})
                claim['credited']=True
                self.corporate_ledger.append({'day':day,
                    'kind':'STOCK_DIVIDEND_SHARES_LISTED' if claim['share_kind']=='STOCK_DIVIDEND' else 'CAPITAL_SHARES_LISTED',
                    'event_id':claim['event_id'],'quantity':claim['quantity']})
        self._finish(day,0)
