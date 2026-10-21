"""Separately versioned local allocation-envelope account, never registry proof.

All original tax/clock/cash/listing rules remain those of the stock distribution
account. Only a noninteger component with a bound primary proof and explicit
candidate selection can differ. Source document bytes are authenticated by the
caller; this module reads no files and does not choose a profitable branch.
"""
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

from stock_rsi.raw_share_account import CENT
from stock_rsi.stock_distribution_account import StockDistributionAccount
from stock_rsi.registry_allocation_bounds import allocation_bounds


class AllocationChoiceRequired(ValueError):
    def __init__(self, event_id, instrument, component, registered_quantity, envelope):
        self.event_id = event_id
        self.instrument = instrument
        self.component = component
        self.registered_quantity = registered_quantity
        self.envelope = deepcopy(envelope)
        self.candidates = tuple(envelope['possible_integer_shares'])
        super().__init__('explicit entire-account allocation choice required: '
                         + event_id + ' ' + component + ' ' + str(self.candidates))


class RegistryAllocationAccount(StockDistributionAccount):
    def __init__(self, calendar, initial_cash, distributions=(), *,
                 registry_proofs=None, allocation_choices=None, **kwargs):
        super().__init__(calendar, initial_cash, distributions, **kwargs)
        proofs = {} if registry_proofs is None else registry_proofs
        choices = {} if allocation_choices is None else allocation_choices
        if type(proofs) is not dict or type(choices) is not dict:
            raise ValueError('explicit event/component proof and choice maps required')
        self.registry_proofs = deepcopy(proofs)
        self.allocation_choices = deepcopy(choices)
        self.allocation_audit = []
        by_id = {event.event_id: event for event in self.events}
        for event_id, components in self.registry_proofs.items():
            if (event_id not in by_id or type(components) is not dict or not components
                    or not set(components) <= {'capital', 'stock'}):
                raise ValueError('registry proof must name an existing event and supported component')
            for component, proof in components.items():
                self._bound_envelope(by_id[event_id], component, proof, 0)
        for event_id, components in self.allocation_choices.items():
            if (event_id not in by_id or type(components) is not dict or not components
                    or not set(components) <= set(self.registry_proofs.get(event_id, {}))
                    or any(type(v) is not int or v < 0 for v in components.values())):
                raise ValueError('allocation choices require matching primary proofs and strict integer values')

    @staticmethod
    def _component_ratio(event, component):
        return event.capital_per_share if component == 'capital' else getattr(event, 'stock_per_share', Decimal(0))

    @classmethod
    def _bound_envelope(cls, event, component, proof, quantity):
        # Document availability is evaluated at the actual ex-date opening,
        # not a later audit clock. The event itself remains immutable.
        at = datetime.combine(event.ex_date, time(9, 30), tzinfo=timezone(timedelta(hours=8)))
        envelope = allocation_bounds(proof, quantity, as_of=at)
        ratio = cls._component_ratio(event, component)
        if (proof['event_id'] != event.event_id or proof['issuer'] != event.instrument
                or proof['component'] != component or proof['record_date'] != event.recorded.isoformat()
                or proof['ex_date'] != event.ex_date.isoformat()
                or proof['published_on'] != event.announced.isoformat()
                or ratio <= 0 or Fraction(proof['quoted_per10']) / 10 != Fraction(ratio)):
            raise ValueError('primary allocation proof does not match immutable event identity, dates or component ratio')
        return envelope

    def start_day(self, day):
        if not self._check_clock(day, 0):
            return
        prepared = []
        # Every current event's strict record/tax/reserve checks precede all
        # choice requests. No payment, share, clock or audit mutation occurs here.
        for event in self.events:
            if event.ex_date != day:
                continue
            if event.event_id not in self.entitlements and event.recorded >= self.calendar.days[0]:
                raise ValueError('record-date ownership was not observed')
            quantity = self.entitlements.get(event.event_id, 0)
            if type(quantity) is not int or quantity < 0:
                raise ValueError('invalid registered integer inventory')
            stock = getattr(event, 'stock_per_share', Decimal(0))
            income = getattr(event, 'stock_taxable_income_per_share', Decimal(0))
            if quantity and event.capital_per_share > 0 and event.capital_tax_exempt_verified is not True:
                raise ValueError('applicable capital transfer tax treatment is unverified')
            if quantity and stock > 0 and (getattr(event, 'stock_tax_basis_verified', False) is not True or income <= 0):
                raise ValueError('applicable stock dividend tax basis is unverified')
            capital_shares, stock_shares = event.capital_per_share * quantity, stock * quantity
            gross = (event.cash_per_share * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
            stock_income = (income * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
            reserve = ((gross + stock_income) * self.tax_reserve_rate).quantize(CENT, rounding=ROUND_HALF_UP)
            if reserve > gross:
                raise ValueError('stock tax stress exceeds cash distribution; liability settlement unsupported')
            prepared.append((event, quantity, capital_shares, stock_shares, gross, stock_income, reserve))
        actions, pending_audit = [], []
        for event, quantity, capital_shares, stock_shares, gross, stock_income, reserve in prepared:
            amounts = {}
            for component, nominal in (('capital', capital_shares), ('stock', stock_shares)):
                selections = self.allocation_choices.get(event.event_id, {})
                if nominal == nominal.to_integral_value():
                    if component in selections and (type(selections[component]) is not int or selections[component] != int(nominal)):
                        raise ValueError('allocation choice cannot override an original integer entitlement')
                    amounts[component] = int(nominal)
                    continue
                proof = self.registry_proofs.get(event.event_id, {}).get(component)
                if proof is None:
                    raise ValueError('fractional corporate entitlement needs registry allocation evidence')
                envelope = self._bound_envelope(event, component, proof, quantity)
                if component not in selections:
                    raise AllocationChoiceRequired(event.event_id, event.instrument, component, quantity, envelope)
                chosen = selections[component]
                if type(chosen) is not int or chosen not in envelope['possible_integer_shares']:
                    raise ValueError('explicit allocation choice is outside the entire-account primary envelope')
                amounts[component] = chosen
                pending_audit.append({
                    'event_id': event.event_id, 'instrument': event.instrument,
                    'recorded': event.recorded.isoformat(), 'ex_date': event.ex_date.isoformat(),
                    'component': component, 'registered_quantity': quantity,
                    'ratio_per_original_share': str(self._component_ratio(event, component)),
                    'nominal_entitlement': str(nominal), 'candidates': list(envelope['possible_integer_shares']),
                    'chosen_integer_quantity': chosen, 'registry_proof_sha256': envelope['proof_sha256'],
                    'as_of': envelope['as_of'], 'envelope': deepcopy(envelope),
                })
            actions.append((event, quantity, amounts['capital'], amounts['stock'], gross, stock_income, reserve))
        # Identical original payment, listing, record-date T+1 and reserve math.
        # All current events and choices have passed before the first mutation.
        for claim in self.cash_claims:
            if not claim['paid'] and claim['available_on'] == day:
                self.broker.cash += claim['net'];claim['paid'] = True
                self.corporate_ledger.append({'day': day, 'kind': 'NET_DIVIDEND_CASH_AVAILABLE',
                    'event_id': claim['event_id'], 'cash_delta': claim['net']})
        for event, quantity, capital, stock, gross, income, reserve in actions:
            if gross:
                available = next((at for at in self.calendar.days if at > event.pay_date), None)
                self.cash_claims.append({'event_id': event.event_id, 'instrument': event.instrument,
                    'gross': gross, 'reserve': reserve, 'net': gross - reserve, 'available_on': available, 'paid': False})
            for amount, kind in ((capital, 'CAPITAL_TRANSFER'), (stock, 'STOCK_DIVIDEND')):
                if amount:
                    self.stock_claims.append({'event_id': event.event_id, 'instrument': event.instrument,
                        'quantity': amount, 'listed': event.listed, 'recorded': event.recorded,
                        'credited': False, 'share_kind': kind})
            self.corporate_ledger.append({'day': day, 'kind': 'EX_DATE_ENTITLEMENT', 'event_id': event.event_id,
                'instrument': event.instrument, 'registered_quantity': quantity, 'cash_gross': gross,
                'stress_tax_reserve': reserve, 'capital_shares': capital, 'stock_shares': stock, 'taxable_stock_income': income})
        for claim in self.stock_claims:
            if not claim['credited'] and claim['listed'] <= day:
                self.broker.positions.setdefault(claim['instrument'], []).append({
                    'quantity': claim['quantity'], 'bought_on': claim['recorded'], 'price': Decimal(0)})
                claim['credited'] = True
                self.corporate_ledger.append({'day': day,
                    'kind': 'STOCK_DIVIDEND_SHARES_LISTED' if claim['share_kind'] == 'STOCK_DIVIDEND' else 'CAPITAL_SHARES_LISTED',
                    'event_id': claim['event_id'], 'quantity': claim['quantity']})
        self._finish(day, 0)
        self.allocation_audit.extend(pending_audit)
