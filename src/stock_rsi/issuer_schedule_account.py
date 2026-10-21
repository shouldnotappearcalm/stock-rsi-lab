"""One issuer-schedule engineering scenario; never a statutory exemption proof.

The frozen stock account and all source flags remain unchanged. This separately
versioned account duplicates its start-day implementation to keep prior method
hashes and failure artifacts immutable. Only a single admission check differs;
scenario provenance stays in an evaluator-only ledger.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from stock_rsi.raw_share_account import CENT
from stock_rsi.stock_distribution_account import StockDistributionAccount

CLASSIFICATION = 'ISSUER_FORMAL_TAX_SCHEDULE_COMPOSITE_INFERENCE'
EVENT_ID = '9209326edbab25fc20575c17d79d5059ac14cdabb28e3a196617944c3cbff3d7'
EVENT_SHA = 'ddaec3e6088254e65a11c2e0c2fcad40bd35d4c405f1319b868b9362ccbf35b4'
SOURCE_NAMES = ('low-beta60-corporate-reviewed-horizon-20261021/SZ000937-20260611.pdf',
    'low-beta60-corporate-reviewed-horizon-20261021/SZ000937-20260827.pdf',
    'low-beta60-capital-tax-regulations-20261021/sat-1997-198.html',
    'low-beta60-capital-tax-regulations-20261021/sat-1998-289.html')
EVIDENCE_NAMES = ('experiments/qlib/low-beta60-capital-tax-evidence-proposal.json',
    'experiments/qlib/low-beta60-capital-tax-evidence-adequacy-review.json',
    'experiments/qlib/low-beta60-capital-tax-regulation-capture-manifest.json')

def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def event_sha(event):return hashlib.sha256(json.dumps(asdict(event),sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

@dataclass(frozen=True)
class ScheduleEvidence:
    event_sha256: str
    registry_sha256: str
    sources: tuple
    classification: str = CLASSIFICATION
    statutory_exemption_verified: bool = False


def load_schedule_evidence(registry, source_root, repo_root, events):
    if (registry['status'] != 'FROZEN_EVENT_SPECIFIC_ISSUER_SCHEDULE_ENGINEERING_SCENARIO'
            or registry['classification'] != CLASSIFICATION
            or registry['investor_scope'] != 'ORDINARY_UNRESTRICTED_INDIVIDUAL'
            or registry['statutory_exemption_verified'] is not False
            or registry['strict_source_events_changed'] is not False
            or registry['retrospective_evidence_evaluator_only'] is not True
            or registry['tax_model'] != 'FLAT20PERCENT_CASH_AND_VERIFIED_STOCK_INCOME_NO_ADDITIONAL_CAPITAL_RESERVE'
            or hashlib.sha256(json.dumps(registry['event'],sort_keys=True,separators=(',',':')).encode()).hexdigest() != EVENT_SHA):
        raise ValueError('fixed event-specific conditional interpretation required')
    matching = [e for e in events if e.event_id == EVENT_ID]
    if len(matching) != 1 or event_sha(matching[0]) != EVENT_SHA:
        raise ValueError('exact single unchanged source event required')
    bound = []
    for field, root, required in (('source_sha256', Path(source_root), SOURCE_NAMES),
                                  ('public_evidence_sha256', Path(repo_root), EVIDENCE_NAMES)):
        if set(registry[field]) != set(required):raise ValueError('complete fixed evidence scope required')
        for name, expected in registry[field].items():
            if file_sha(root/name) != expected:raise ValueError('issuer-schedule source or review bytes changed')
            bound.append((name,expected))
    return ScheduleEvidence(EVENT_SHA,hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(',',':')).encode()).hexdigest(),tuple(sorted(bound)))


class IssuerScheduleAccount(StockDistributionAccount):
    def __init__(self, calendar, initial_cash, distributions=(), *, schedule_evidence, **kwargs):
        super().__init__(calendar,initial_cash,distributions,**kwargs)
        if self.tax_reserve_rate != Decimal('.2'):raise ValueError('unchanged20percent reserve required')
        if schedule_evidence is not None:
            if (not isinstance(schedule_evidence,ScheduleEvidence)
                    or schedule_evidence.classification != CLASSIFICATION
                    or schedule_evidence.statutory_exemption_verified is not False
                    or schedule_evidence.event_sha256 != EVENT_SHA
                    or len([e for e in self.events if e.event_id == EVENT_ID and event_sha(e) == EVENT_SHA]) != 1):
                raise ValueError('scenario proof bound to another event or unsupported classification')
        self.schedule_evidence = schedule_evidence
        self.scenario_ledger = []

    def supports_conditional_event(self,event):
        return self.schedule_evidence is not None and event.event_id == EVENT_ID and event_sha(event) == EVENT_SHA

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
            if quantity and event.capital_per_share>0 and event.capital_tax_exempt_verified is not True and not self.supports_conditional_event(event):
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
        for event,quantity,capital,stock,gross,income,reserve in actions:
            if quantity and self.supports_conditional_event(event):
                self.scenario_ledger.append({'day':day,'event_id':event.event_id,'classification':CLASSIFICATION,
                    'registered_quantity':quantity,'capital_shares':capital,'cash_gross':gross,'stress_tax_reserve':reserve,
                    'statutory_exemption_verified':False,'original_strict_flag':event.capital_tax_exempt_verified,
                    'registry_semantic_sha256':self.schedule_evidence.registry_sha256})
        self._finish(day,0)
