"""Classic 54-card Dou Dizhu. Ranks 3..15=3..2, 16/17=jokers.

Single airplane wings may include pairs, but not body ranks or both jokers.
Four-with-two singles may be a pair, but cannot be the two jokers together.
Pair wings have distinct ranks; 2/jokers never form a sequence.
"""
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations

NAMES = {**{i: str(i) for i in range(3, 11)}, 11: 'J', 12: 'Q', 13: 'K', 14: 'A', 15: '2', 16: '小王', 17: '大王'}
KINDS = {'single':'单张','pair':'对子','triple':'三张','triple_single':'三带一',
         'triple_pair':'三带二','straight':'顺子','pairs':'连对','plane':'飞机',
         'plane_single':'飞机带单','plane_pair':'飞机带对','four_single':'四带二单',
         'four_pair':'四带两对','bomb':'炸弹','rocket':'王炸'}


def rank(card):
    if type(card) is not int or not 0 <= card < 54:
        raise ValueError('无效的牌。')
    return card // 4 + 3 if card < 52 else card - 36


def ranks(cards):
    return tuple(sorted(rank(c) for c in cards))


def label(cards):
    return ' '.join(NAMES[r] for r in cards) if cards else '不出'


@dataclass(frozen=True)
class Move:
    cards: tuple
    kind: str
    main: int
    length: int = 1

    @property
    def name(self):
        return KINDS[self.kind]


def _runs(counts, multiplicity, minimum):
    for start in range(3, 15):
        end = start
        while end <= 14 and counts[end] >= multiplicity:
            end += 1
        for size in range(minimum, end - start + 1):
            yield tuple(range(start, start + size))


def _wings(counts, n, pairs=False):
    if pairs:
        yield from (tuple(r for r in rs for _ in range(2))
                    for rs in combinations([r for r in sorted(counts) if counts[r] >= 2], n))
        return
    # Enumerate rank multisets, rather than physical-card combinations.
    keys = sorted(r for r, count in counts.items() if count)
    def visit(i, left, chosen):
        if not left:
            if not (16 in chosen and 17 in chosen):
                yield tuple(chosen)
            return
        if i == len(keys):
            return
        r = keys[i]
        for take in range(min(left, counts[r]) + 1):
            yield from visit(i + 1, left - take, chosen + [r] * take)
    yield from visit(0, n, [])


@lru_cache(maxsize=4096)
def all_moves(hand):
    """Generate every distinct rank action; order gives canonical ambiguous planes."""
    count = Counter(hand)
    result = {}
    def add(cards, kind, main, length=1):
        cards = tuple(sorted(cards))
        result.setdefault(cards, Move(cards, kind, main, length))
    for r in sorted(count):
        add([r], 'single', r)
        for n, kind in [(2,'pair'), (3,'triple'), (4,'bomb')]:
            if count[r] >= n:
                add([r]*n, kind, r)
        if count[r] >= 3:
            for k in sorted(count):
                if k == r:
                    continue
                add([r]*3+[k], 'triple_single', r)
                if count[k] >= 2:
                    add([r]*3+[k]*2, 'triple_pair', r)
    if count[16] and count[17]:
        add([16,17], 'rocket', 17)
    for mult, minimum, kind in [(1,5,'straight'),(2,3,'pairs'),(3,2,'plane')]:
        for body in _runs(count, mult, minimum):
            cards = [r for r in body for _ in range(mult)]
            add(cards, kind, body[-1], len(body))
    # Higher main body resolves an ambiguous airplane deterministically.
    for body in sorted(_runs(count,3,2), key=lambda b:(len(b),b[-1]), reverse=True):
        rest = Counter({r:n for r,n in count.items() if r not in body})
        cards = [r for r in body for _ in range(3)]
        for pairs, kind in [(False,'plane_single'),(True,'plane_pair')]:
            for wings in _wings(rest,len(body),pairs):
                add(cards+list(wings),kind,body[-1],len(body))
    for r in sorted(count):
        if count[r] == 4:
            rest = Counter({k:n for k,n in count.items() if k != r})
            for pairs,kind in [(False,'four_single'),(True,'four_pair')]:
                for wings in _wings(rest,2,pairs):
                    add([r]*4+list(wings),kind,r)
    return tuple(sorted(result.values(),key=lambda m:(len(m.cards),m.main,m.cards)))


def classify(cards):
    cards = tuple(sorted(cards))
    if not cards or len(cards) > 20 or any(type(r) is not int or not 3 <= r <= 17 for r in cards):
        return None
    c = Counter(cards)
    if any(n > (1 if r >= 16 else 4) for r,n in c.items()):
        return None
    return next((m for m in all_moves(cards) if m.cards == cards),None)


def beats(move, target):
    if target is None:
        return True
    if target.kind == 'rocket':
        return False
    if move.kind == 'rocket':
        return True
    if move.kind == 'bomb' and target.kind != 'bomb':
        return True
    return (move.kind == target.kind and len(move.cards) == len(target.cards)
            and move.length == target.length and move.main > target.main)


def legal_moves(hand, target=None):
    return tuple(m for m in all_moves(tuple(sorted(hand))) if beats(m,target))


def subtract(hand, cards):
    rest = list(hand)
    for r in cards:
        rest.remove(r)
    return tuple(rest)
