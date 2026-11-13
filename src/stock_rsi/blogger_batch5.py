"""Fixed published daily rules. The caller supplies completed sessions only."""
import math

CODE = 'SH510050'
NAMES = ('hill5200', 'swanson32')


def evaluate(name, closes, opens, held, state):
    """Return the target and state; account sizing/execution are separate."""
    if name not in NAMES or type(held) is not bool or type(state) is not bool:
        raise ValueError('declared strategy and boolean state required')
    if len(closes) != 200 or len(opens) != 3 or any(
        type(p) not in (int, float) or not math.isfinite(p) or p <= 0
        for p in (*closes, *opens)
    ):
        raise ValueError('200 completed closes and three completed opens required')
    if name == 'hill5200':
        fast = math.fsum(closes[-5:]) / 5
        slow = math.fsum(closes) / 200
        bullish = fast >= 1.01 * slow
        bearish = fast <= .99 * slow
        state = bullish or (state and not bearish)
        target = state
        detail = {'sma5': fast, 'sma200': slow, 'bullish': bullish, 'bearish': bearish}
    else:
        down = all(c < o for c, o in zip(closes[-3:], opens))
        up = all(c > o for c, o in zip(closes[-2:], opens[-2:]))
        state = held and (state or up)
        target = (held and not state) or (not held and down)
        detail = {'three_down_bodies': down, 'two_up_bodies': up}
    return {'leader': CODE if target else None, 'state_after': state, 'details': detail}
