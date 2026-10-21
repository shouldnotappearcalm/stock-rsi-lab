"""Conservative local integer envelopes, not certified registry allocations.

Only proof metadata and exact rational arithmetic are consumed. The caller must
bind the primary document bytes and event identity separately. A display's last
printed digit is used as a symmetric engineering uncertainty assumption, not as
an issuer-certified precision statement. Candidates are not probabilities, joint
registry outcomes, FIFO-lot rounding, or an ordering of portfolio returns.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import PurePath
import re

CONTRACT = 'PRIMARY_LARGEST_REMAINDER_LOCAL_ENVELOPE_V1'
FRACTION_METHOD = 'LARGEST_REMAINDER_DESC_RANDOM_TIES'
PRECISION_ASSUMPTION = 'ONE_LAST_DIGIT_SYMMETRIC_ENGINEERING_ASSUMPTION'
SHANGHAI = timezone(timedelta(hours=8))
PROOF_FIELDS = frozenset({
    'contract', 'issuer', 'event_id', 'record_date', 'ex_date', 'component',
    'source_file', 'source_sha256', 'published_on', 'available_at',
    'actual_arrival_verified', 'eligible_count', 'declared_total_shares',
    'quoted_per10', 'fraction_method', 'quoted_precision_bound',
})


def _require(value, message):
    if not value:
        raise ValueError(message)


def _date(value):
    _require(type(value) is str, 'canonical date string required')
    parsed = date.fromisoformat(value)
    _require(parsed.isoformat() == value, 'canonical date string required')
    return parsed


def _instant(value):
    _require(isinstance(value, (str, datetime)), 'aware evidence clock required')
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             'aware evidence clock required')
    return parsed.astimezone(SHANGHAI)


def fraction_pair(value):
    """Exact JSON-compatible numerator/denominator strings, never a float."""
    return (str(value.numerator), str(value.denominator))


def allocation_bounds(proof, registered_quantity, *, as_of):
    """Bound one entire registered account; reject rather than trim candidates.

    The local envelope is floor(q*lower_ratio)..ceil(q*upper_ratio), inclusive.
    The exact declared-total/eligible-count ratio must lie inside the display
    envelope, but does not shrink it. At most three integer candidates are
    allowed; wider ambiguity and a candidate above the declared global total
    fail closed. q=0 produces only zero after all metadata is validated.
    """
    _require(type(proof) is dict and set(proof) == PROOF_FIELDS,
             'exact event-bound primary allocation proof required')
    _require(proof['contract'] == CONTRACT
             and proof['fraction_method'] == FRACTION_METHOD
             and proof['quoted_precision_bound'] == PRECISION_ASSUMPTION,
             'registered allocation and engineering precision contracts required')
    _require(proof['actual_arrival_verified'] is False,
             'actual arrival must remain uncertified')
    _require(type(proof['issuer']) is str
             and re.fullmatch(r'(?:SH|SZ)[0-9]{6}', proof['issuer']) is not None,
             'canonical primary issuer required')
    _require(type(proof['event_id']) is str and bool(proof['event_id'])
             and proof['event_id'].strip() == proof['event_id']
             and all(ord(c) >= 32 for c in proof['event_id']),
             'explicit unchanged source event identity required')
    _require(proof['component'] in ('capital', 'stock'),
             'only a single capital or stock component is supported')
    name, checksum = proof['source_file'], proof['source_sha256']
    _require(type(name) is str and bool(name) and PurePath(name).name == name
             and name not in ('.', '..') and '\\' not in name
             and type(checksum) is str and re.fullmatch('[0-9a-f]{64}', checksum) is not None,
             'primary document basename and SHA256 required')
    published, record, ex = map(_date, (proof['published_on'], proof['record_date'], proof['ex_date']))
    available, observed = _instant(proof['available_at']), _instant(as_of)
    _require(published <= record < ex and published <= available.date() and available <= observed,
             'primary dates or as-of availability are inconsistent')
    eligible, total = proof['eligible_count'], proof['declared_total_shares']
    _require(type(eligible) is int and eligible > 0 and type(total) is int and total > 0,
             'positive integer primary counts required; booleans are not counts')
    _require(type(registered_quantity) is int and 0 <= registered_quantity <= eligible,
             'entire registered account quantity must be an integer within eligible count')
    quoted = proof['quoted_per10']
    _require(type(quoted) is str
             and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', quoted) is not None,
             'canonical finite positive per10 decimal string required')
    quote = Fraction(quoted)
    _require(quote > 0, 'positive per10 component amount required')
    digits = len(quoted.split('.')[1]) if '.' in quoted else 0
    quantum = Fraction(1, 10 ** digits)
    quoted_ratio, exact_ratio = quote / 10, Fraction(total, eligible)
    lower, upper = (quote - quantum) / 10, (quote + quantum) / 10
    _require(0 <= lower <= exact_ratio <= upper,
             'declared global ratio is outside the assumed display precision envelope')
    low_quantity, high_quantity = registered_quantity * lower, registered_quantity * upper
    first = low_quantity.numerator // low_quantity.denominator
    last = -(-high_quantity.numerator // high_quantity.denominator)
    _require(last - first <= 2, 'precision ambiguity exceeds three local integer candidates')
    _require(0 <= first <= last <= total,
             'local candidate exceeds the declared total; reject without clipping')
    canonical = json.dumps(proof, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return {
        'contract': CONTRACT,
        'proof': deepcopy(proof),
        'proof_sha256': sha256(canonical.encode()).hexdigest(),
        'registered_quantity': registered_quantity,
        'as_of': observed.isoformat(),
        'quoted_per10': quoted,
        'one_last_digit_per10': fraction_pair(quantum),
        'quoted_ratio': fraction_pair(quoted_ratio),
        'exact_total_ratio': fraction_pair(exact_ratio),
        'exact_total_ratio_minus_quoted_ratio': fraction_pair(exact_ratio - quoted_ratio),
        'lower_ratio': fraction_pair(lower),
        'upper_ratio': fraction_pair(upper),
        'lower_entitlement': fraction_pair(low_quantity),
        'upper_entitlement': fraction_pair(high_quantity),
        'exact_total_ratio_entitlement': fraction_pair(registered_quantity * exact_ratio),
        'possible_integer_shares': list(range(first, last + 1)),
        'candidate_reason': 'ALL_INTEGERS_FROM_FLOOR_LOWER_TO_CEIL_UPPER_ENTIRE_REGISTERED_ACCOUNT',
        'rounding_scope': 'ENTIRE_REGISTERED_ACCOUNT_NOT_FIFO_LOTS',
        'primary_document_bytes_verified_by_this_module': False,
        'quoted_precision_is_certified': False,
        'actual_registry_allocation_certified': False,
        'probabilities_certified': False,
        'globally_jointly_feasible': False,
        'portfolio_return_ordering_claimed': False,
        'account_replay_admitted': False,
    }
