"""Authoritative round state. Policy receives Observation, never Game or a seed."""
from dataclasses import dataclass
import random
from collections import Counter
from .rules import rank, ranks, classify, beats, label


@dataclass(frozen=True)
class Observation:
    seat: int
    hand: tuple
    counts: tuple
    landlord: int | None
    target: tuple
    leader: int | None
    passes: int
    history: tuple  # (seat, rank tuple), all publicly played actions
    bottom: tuple
    phase: str
    bids: tuple
    high_bid: int

    def same_team(self, a, b):
        return a == b or (a != self.landlord and b != self.landlord)


class Game:
    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.SystemRandom()
        self.version = 0
        self.round = 0
        self.scores = [0,0,0]
        self.last_ai = None
        self.deal()

    def deal(self):
        deck = list(range(54))
        self.rng.shuffle(deck)
        self.hands = [sorted(deck[i*17:(i+1)*17],key=lambda c:(rank(c),c)) for i in range(3)]
        self.bottom = deck[51:]
        self.phase = 'bid'
        self.first_bid = (self.first_bid+1)%3 if hasattr(self, "first_bid") else self.rng.randrange(3)
        self.turn = self.first_bid
        self.bids = []
        self.high_bid = 0
        self.landlord = None
        self.target = None
        self.leader = None
        self.passes = 0
        self.history = []
        self.play_counts = [0,0,0]
        self.bombs = 0
        self.winner = None
        self.settlement = None
        self.round += 1
        self.message = '请叫分；三家都不叫时重新发牌。'
        self.last_ai = None

    def observation(self, seat):
        return Observation(seat, ranks(self.hands[seat]), tuple(map(len,self.hands)),
                           self.landlord, self.target.cards if self.target else (),
                           self.leader,self.passes,tuple((s,tuple(cs)) for s,cs in self.history),
                           ranks(self.bottom) if self.phase != 'bid' else (),
                           self.phase,tuple(self.bids),self.high_bid)

    def bid(self, seat, value):
        if self.phase != 'bid' or seat != self.turn:
            raise ValueError('现在不是你的叫分回合。')
        if type(value) is not int or value not in range(4) or (value and value <= self.high_bid):
            raise ValueError('只能不叫，或叫比当前更高的 1 / 2 / 3 分。')
        self.bids.append((seat,value))
        if value:
            self.high_bid,self.landlord = value,seat
        self.version += 1
        if value == 3 or len(self.bids) == 3:
            if not self.high_bid:
                self.deal()
                self.message = '三家都不叫，已重新发牌。'
                return
            self.hands[self.landlord] = sorted(self.hands[self.landlord]+self.bottom,key=lambda c:(rank(c),c))
            self.phase,self.turn = 'play',self.landlord
            self.message = '地主已确定，由地主先出牌。'
        else:
            self.turn = (seat+1)%3

    def play(self, seat, cards):
        if self.phase != 'play' or seat != self.turn:
            raise ValueError('现在不是你的出牌回合。')
        if not isinstance(cards,list) or any(type(c) is not int for c in cards) or len(set(cards)) != len(cards):
            raise ValueError('出牌包含重复或无效的牌。')
        if not set(cards) <= set(self.hands[seat]):
            raise ValueError('只能打出自己手中的牌。')
        move = classify(ranks(cards)) if cards else None
        if not cards and self.target is None:
            raise ValueError('新一轮领出不能不出。')
        if cards and (move is None or not beats(move,self.target)):
            raise ValueError('牌型不合法，或未能压过当前牌。')
        self.history.append((seat,ranks(cards)))
        self.version += 1
        if cards:
            self.hands[seat] = [c for c in self.hands[seat] if c not in set(cards)]
            self.target,self.leader,self.passes = move,seat,0
            self.play_counts[seat] += 1
            self.bombs += move.kind in ('bomb','rocket')
            self.message = f'{move.name} · {label(move.cards)}'
            if not self.hands[seat]:
                self.finish(seat)
                return
        else:
            self.passes += 1
            self.message = '不出'
            if self.passes == 2:
                self.target,self.passes = None,0
                self.message = '其他两家不出，由上一手玩家重新领出。'
        self.turn = (seat+1)%3

    def finish(self, seat):
        self.phase,self.winner = 'over',seat
        landlord_won = seat == self.landlord
        spring = (all(self.play_counts[s] == 0 for s in range(3) if s != self.landlord)
                  if landlord_won else self.play_counts[self.landlord] == 1)
        multiplier = 2 ** (self.bombs + int(spring))
        base = self.high_bid * multiplier
        delta = [(-base if landlord_won else base) for _ in range(3)]
        delta[self.landlord] = base * (2 if landlord_won else -2)
        self.scores = [a+b for a,b in zip(self.scores,delta)]
        self.settlement = {'delta':delta,'bid':self.high_bid,'bombs':self.bombs,
                           'spring':('春天' if landlord_won else '反春天') if spring else None,
                           'multiplier':multiplier,'landlord_won':landlord_won}
        self.message = ('地主获胜' if landlord_won else '农民共同获胜') + (' · '+self.settlement['spring'] if spring else '')

    def ids_for(self, seat, move):
        needed = Counter(move)
        ids = []
        for card in self.hands[seat]:
            if needed[rank(card)]:
                ids.append(card)
                needed[rank(card)] -= 1
        if any(needed.values()):
            raise ValueError('AI 请求了不在手中的牌。')
        return ids

    def view(self):
        # Only seat 0 is human. No seeds, opponent actions/options or hidden IDs.
        return {'version':self.version,'round':self.round,'phase':self.phase,'turn':self.turn,
                'hand':self.hands[0], 'counts':list(map(len,self.hands)), 'landlord':self.landlord,
                'bottom':self.bottom if self.phase != 'bid' else [],
                'bids':self.bids,'high_bid':self.high_bid,'history':self.history,
                'target':list(self.target.cards) if self.target else [],'leader':self.leader,
                'message':self.message,'scores':self.scores,'settlement':self.settlement,
                'last_ai':({k:v for k,v in self.last_ai.items() if k in
                            {'seat','model','inference_ms','total_ms','intervened','reason'}}
                           if self.last_ai else None),
                'revealed':self.hands if self.phase == 'over' else None}
