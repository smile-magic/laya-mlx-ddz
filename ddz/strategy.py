"""Information-set strategy: public observation in, legal rank action out.

Sampling is a finite heuristic, never access to the real hidden hands. Laya
chooses among near-best candidates; scores below are not calibrated win rates.
"""
from collections import Counter
from functools import lru_cache
import hashlib
import math
import random
import time
from .rules import all_moves, legal_moves, classify, subtract, label, NAMES


@lru_cache(maxsize=32768)
def shape_cost(hand):
    """Cheap decomposition estimate, preserving pairs/triples before singles."""
    if not hand:
        return 0.0
    answers = []
    for sequences_first in (False,True):
        c = Counter(hand)
        groups = 0
        def sequences(mult, minimum):
            nonlocal groups
            for start in range(3,15):
                end = start
                while end <= 14 and c[end] >= mult:
                    end += 1
                if end-start >= minimum:
                    for r in range(start,end):
                        c[r] -= mult
                    groups += 1
        if sequences_first:
            sequences(1,5)
        sequences(3,2)
        sequences(2,3)
        if not sequences_first:
            sequences(1,5)
        singles = sum(n==1 for n in c.values())
        pairs = sum(n==2 for n in c.values())
        triples = sum(n==3 for n in c.values())
        bombs = sum(n==4 for n in c.values())
        # Each independent triple can carry one single or one pair.
        groups += triples+bombs+max(0,singles+pairs-triples)
        answers.append(groups)
    return float(min(answers))


@lru_cache(maxsize=16384)
def exact_turns(hand):
    """Minimum self-only partition for small hands, NOT a game-tree solution."""
    if not hand:
        return 0
    if len(hand)>10:
        return shape_cost(hand)
    if classify(hand):
        return 1
    first=hand[0]
    return 1+min(exact_turns(subtract(hand,m.cards)) for m in all_moves(hand) if first in m.cards)


def allies(a,b,landlord):
    return a==b or (a != landlord and b != landlord)


def move_score(hand, move, seat, landlord, counts, leader, target):
    team_leads = target is not None and allies(seat,leader,landlord)
    enemy_low = min(counts[s] for s in range(3) if not allies(seat,s,landlord))
    if move is None:
        return -2*shape_cost(hand) + (1.15 if team_leads else -.7)
    rest = subtract(hand,move.cards)
    if not rest:
        return 100.0
    score = -2*shape_cost(rest)+len(move.cards)*.045-move.main*.018
    original=Counter(hand)
    for r,n in Counter(move.cards).items():
        if n < original[r] and original[r]>=2:
            score -= .14*(original[r]-n)  # Avoid needlessly splitting combinations.
    if move.kind in ('bomb','rocket'):
        score -= .9
    if team_leads:
        score -= 1.5 if counts[leader]<=5 else .65
    if enemy_low==1:
        if target is None and move.kind=='single':
            score -= 1.6
        elif target is not None and move.kind=='single' and not team_leads:
            score += move.main*.12
    if enemy_low==2 and target is None and move.kind=='pair':
        score -= .75
    # As a farmer, give a nearly-out teammate a low lead they may take.
    if seat!=landlord and target is None:
        teammate=next(s for s in range(3) if s!=seat and s!=landlord)
        if counts[teammate]==1 and move.kind=='single':
            score += 1.1-move.main*.065
    return score


def _seed(obs):
    return int.from_bytes(hashlib.sha256(repr(obs).encode()).digest()[:8],'big')


def sample_hands(obs, rng):
    """Deal unseen cards, respecting public bottom cards still held by landlord."""
    pool=Counter({**{r:4 for r in range(3,16)},16:1,17:1})
    pool.subtract(obs.hand)
    for _,cards in obs.history:
        pool.subtract(cards)
    if any(n<0 for n in pool.values()):
        raise ValueError('公开牌面与手牌不一致。')
    hands=[[] for _ in range(3)]
    hands[obs.seat]=list(obs.hand)
    if obs.landlord != obs.seat:
        known=Counter(obs.bottom)
        for seat,cards in obs.history:
            if seat==obs.landlord:
                known.subtract(cards)
        for r,n in known.items():
            n=max(0,n)
            hands[obs.landlord].extend([r]*n)
            pool[r]-=n
    if any(n<0 for n in pool.values()):
        raise ValueError('底牌约束不一致。')
    unknown=list(pool.elements())
    rng.shuffle(unknown)
    for seat in range(3):
        if seat==obs.seat:
            continue
        take=obs.counts[seat]-len(hands[seat])
        if take<0 or take>len(unknown):
            raise ValueError('剩余张数不一致。')
        hands[seat].extend(unknown[:take])
        del unknown[:take]
    if unknown:
        raise ValueError('未分配牌数不一致。')
    return tuple(tuple(sorted(h)) for h in hands)


def advance(hands, seat, target, leader, passes, move):
    hands=list(hands)
    if move is not None:
        hands[seat]=subtract(hands[seat],move.cards)
        target,leader,passes=move,seat,0
    else:
        passes+=1
        if passes==2:
            target,passes=None,0
    return tuple(hands),(seat+1)%3,target,leader,passes


def rollout(hands, seat, target, leader, passes, landlord, perspective, first, max_plies=54):
    """Cheap public-view policies in a sampled world, common across candidates."""
    hands,seat,target,leader,passes=advance(hands,seat,target,leader,passes,first)
    for _ in range(max_plies):
        for s,h in enumerate(hands):
            if not h:
                return 1.0 if allies(s,perspective,landlord) else 0.0
        options=list(legal_moves(hands[seat],target))
        if target is not None:
            options.append(None)
        counts=tuple(map(len,hands))
        move=max(options,key=lambda m:move_score(hands[seat],m,seat,landlord,counts,leader,target))
        hands,seat,target,leader,passes=advance(hands,seat,target,leader,passes,move)
    own=min(shape_cost(hands[s]) for s in range(3) if allies(s,perspective,landlord))
    enemy=min(shape_cost(hands[s]) for s in range(3) if not allies(s,perspective,landlord))
    return .5 + .25*max(-1,min(1,(enemy-own)/4))


def immediate_loss(hands, obs, move):
    """Can an opponent finish before this player acts again, through passes?"""
    hands,seat,target,leader,passes=advance(hands,obs.seat,classify(obs.target),obs.leader,obs.passes,move)
    for _ in range(2):
        finish=classify(hands[seat])
        if finish is not None and (target is None or finish in legal_moves(hands[seat],target)):
            return 0.0 if allies(seat,obs.seat,obs.landlord) else 1.0
        # This deliberately tests a conservative pass path, not all responses.
        hands,seat,target,leader,passes=advance(hands,seat,target,leader,passes,None)
    return 0.0


def evaluate(obs, samples=6):
    if obs.phase!='play':
        raise ValueError('不是出牌阶段。')
    target=classify(obs.target)
    legal=list(legal_moves(obs.hand,target))
    if target is not None:
        legal.append(None)
    if not legal:
        raise ValueError('没有合法动作。')
    scores={m:move_score(obs.hand,m,obs.seat,obs.landlord,obs.counts,obs.leader,target) for m in legal}
    ordered=sorted(legal,key=lambda m:scores[m],reverse=True)
    # Preserve distinct tactical alternatives before limiting the model choices.
    shortlist=ordered[:2]
    enemy_low=min(obs.counts[s] for s in range(3) if not allies(s,obs.seat,obs.landlord))
    extras=[]
    if target and enemy_low<=2:
        replies=[m for m in ordered if m and m.kind==target.kind]
        if replies:
            extras.append(max(replies,key=lambda m:m.main))
    if target:
        extras.append(None)
    extras.append(next((m for m in ordered if m and m.kind in ('bomb','rocket')),None))
    # Preserve a different action family before spending remaining slots on
    # almost identical sequences/attachments.
    seen={m.kind if m else 'pass' for m in shortlist}
    for m in ordered:
        kind=m.kind if m else 'pass'
        if kind not in seen:
            extras.append(m)
            seen.add(kind)
    for m in extras+ordered:
        if len(shortlist)>=6:
            break
        if m in scores and m not in shortlist:
            shortlist.append(m)
    # A legal move that empties our hand is a team win, independent of hidden cards.
    finishing=next((m for m in legal if m and len(m.cards)==len(obs.hand)),None)
    rng=random.Random(_seed(obs))
    worlds=[sample_hands(obs,rng) for _ in range(samples)]
    rows=[]
    for m in shortlist:
        rest=obs.hand if m is None else subtract(obs.hand,m.cards)
        risk=sum(immediate_loss(h,obs,m) for h in worlds)/samples
        outcome=sum(rollout(h,obs.seat,target,obs.leader,obs.passes,obs.landlord,obs.seat,m) for h in worlds)/samples
        turns=exact_turns(rest)
        score=scores[m]+(shape_cost(rest)-turns)*2+outcome*3.5-risk*5
        rows.append({'move':m,'score':score,'risk':risk,'sample_value':outcome,'turns':turns})
    best=max(rows,key=lambda x:x['score'])
    for row in rows:
        row['eligible'] = row['move']==finishing if finishing else (
            row['score']>=best['score']-.20
            and row['risk']<=best['risk']+1e-9
            and row['sample_value']>=best['sample_value']-.5/samples)
    rows.sort(key=lambda x:x['score'],reverse=True)
    return rows,len(legal)


class Policy:
    def __init__(self, model, samples=6):
        from laya_mlx import Agent
        self.agent=Agent(model,dtype='float16',device='gpu',batch_size=1)
        self.samples=samples
        self.agent.predict('Warm up.',{'ready':{'type':'choice','instructions':'Choose ready.','criteria':['ready','wait']}})

    def choose(self, obs):
        started=time.perf_counter()
        if obs.phase=='bid':
            return self.bid(obs,started)
        rows,total=evaluate(obs,self.samples)
        criteria={}
        for i,row in enumerate(rows):
            m=row['move']
            cards='PASS' if m is None else ' '.join(str(r) for r in m.cards)
            criteria[f'M{i}']=f"{'OK' if row['eligible'] else 'Avoid'} {cards}; groups {row['turns']:g}; risk {row['risk']:.2f}; value {row['sample_value']:.2f}"
        # Use compact public summaries to stay inside this checkpoint's context.
        unseen=Counter({**{r:4 for r in range(3,16)},16:1,17:1})
        unseen.subtract(obs.hand)
        for _,cs in obs.history:
            unseen.subtract(cs)
        recent=';'.join(f'{s}:{list(cs)}' for s,cs in obs.history[-8:])
        state=(f'Dou Dizhu. Ranks 3..14=3..A,15=2,16/17=jokers. You seat {obs.seat}; landlord {obs.landlord}. '
               'Landlord plays alone; both farmers win together. Other hands are hidden. '
               f'Your hand {list(obs.hand)}. Counts {list(obs.counts)}. Target {list(obs.target)} from {obs.leader}. '
               f'Unseen rank counts {dict(sorted((r,n) for r,n in unseen.items() if n>0))}. '
               f'Recent public plays {recent}. Scores are heuristic, not true win probabilities.')
        q={'play':{'type':'choice','instructions':'Choose best OK move. Finish hand, protect team, avoid immediate loss.','criteria':criteria}}
        tick=time.perf_counter()
        result=self.agent.predict(state,q)
        inference=(time.perf_counter()-tick)*1000
        probabilities=self.probabilities(result,'play',criteria)
        proposed=max(range(len(rows)),key=lambda i:probabilities[f'M{i}'])
        selected=max((i for i,row in enumerate(rows) if row['eligible']),key=lambda i:probabilities[f'M{i}'])
        move=rows[selected]['move']
        # Public-safe diagnostics: never return unseen candidate cards or a private prompt.
        return (list(move.cards) if move else []),{
            'seat':obs.seat,'model':True,'inference_ms':round(inference,1),
            'total_ms':round((time.perf_counter()-started)*1000,1),'intervened':proposed!=selected,
            'reason':'模型在策略筛选后的合法动作中选择', 'legal_count':total,
            'input_tokens':result.get('usage',{}).get('input_tokens')}

    @staticmethod
    def probabilities(result,key,criteria):
        p=result['answers'][key]['probabilities']
        if set(p)!=set(criteria) or any(not math.isfinite(v) or not 0<=v<=1 for v in p.values()) or sum(p.values())<=0:
            raise RuntimeError('模型概率无效。')
        return p

    def bid(self,obs,started):
        c=Counter(obs.hand)
        strength=c[17]*1.6+c[16]+c[15]*.65+c[14]*.2+sum(n==4 for n in c.values())*1.6
        if c[16] and c[17]:
            strength+=1.5
        strength+=max(0,7-shape_cost(obs.hand))*.45
        ceiling=3 if strength>=5.5 else 2 if strength>=3.5 else 1 if strength>=2.2 else 0
        legal=[0]+list(range(obs.high_bid+1,4))
        allowed=[b for b in legal if b<=ceiling]
        criteria={str(b):f"{'OK' if b in allowed else 'Avoid'} {'pass' if b==0 else 'bid '+str(b)}" for b in legal}
        tick=time.perf_counter()
        result=self.agent.predict(f'Dou Dizhu bidding. Hand ranks {list(obs.hand)}; 15=2,16/17=jokers. '
                                  f'Hand strength heuristic {strength:.1f}. Current bid {obs.high_bid}.',
                                  {'bid':{'type':'choice','instructions':'Choose an OK bid appropriate to hand strength.','criteria':criteria}})
        p=self.probabilities(result,'bid',criteria)
        proposed=max(legal,key=lambda b:p[str(b)])
        value=max(allowed,key=lambda b:p[str(b)])
        return value,{'seat':obs.seat,'model':True,'inference_ms':round((time.perf_counter()-tick)*1000,1),
                      'total_ms':round((time.perf_counter()-started)*1000,1),'intervened':value!=proposed,
                      'reason':'模型结合手牌强度选择叫分'}
