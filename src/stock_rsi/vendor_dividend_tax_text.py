"""Literal vendor net-cash alternatives, never an account tax decision."""
from decimal import Decimal
import re

NUMBER=re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z')


def parse_net_cash(text,gross):
    if type(text) is not str or type(gross) is not str:raise ValueError('literal strings required')
    result={'source_text':text,'gross_source_text':gross,'options':[],'selected_net_cash':None,'tax_treatment_admitted':False}
    if not text:return {**result,'status':'UNKNOWN_EMPTY_SOURCE_TEXT'}
    try:maximum=Decimal(gross)
    except ArithmeticError as exc:raise ValueError('explicit finite gross cash required') from exc
    if not maximum.is_finite() or maximum<0:raise ValueError('explicit finite nonnegative gross cash required')
    parts=text.split('或')
    if not all(NUMBER.fullmatch(p) for p in parts):raise ValueError('unsupported literal net-cash text')
    if any(Decimal(p)>maximum for p in parts):raise ValueError('net-cash option exceeds gross cash')
    return {**result,'status':'LITERAL_ALTERNATIVES_UNSELECTED' if len(parts)>1 else 'LITERAL_SINGLE_AMOUNT_NOT_ACCOUNT_TAX', 'options':parts}
