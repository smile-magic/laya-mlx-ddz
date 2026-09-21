import os
import random
from dataclasses import replace
import unittest
from collections import Counter
from ddz.game import Game, Observation
from ddz.rules import classify, legal_moves, ranks
from ddz.strategy import Policy, evaluate, sample_hands, exact_turns, shape_cost, control_cost, controlled_finish


def scenario(hand, others, landlord=1, target=(), leader=None):
    full=Counter({**{r:4 for r in range(3,16)},16:1,17:1})
    for h in [hand,*others]:full.subtract(h)
    full.subtract(target)
    assert all(n>=0 for n in full.values())
    history=((2,tuple(sorted(full.elements()))),)+(((leader,tuple(target)),) if target else ())
    return Observation(0,tuple(sorted(hand)),(len(hand),len(others[0]),len(others[1])),landlord,tuple(target),leader,0,history,(),'play',(),1)


class CaptureAgent:
    def __init__(self,prefer_avoid=False):self.prefer_avoid=prefer_avoid;self.calls=[]
    def predict(self,state,questions):
        self.calls.append((state,questions));key=next(iter(questions));criteria=questions[key]['criteria']
        selected=next((k for k,v in criteria.items() if v.startswith('Avoid')),next(iter(criteria))) if self.prefer_avoid else next(iter(criteria))
        return {'answers':{key:{'probabilities':{k:float(k==selected) for k in criteria}}},'usage':{'input_tokens':500}}


def fake_policy(avoid=False):
    p=Policy.__new__(Policy);p.agent=CaptureAgent(avoid);p.samples=4;return p


class StrategyTests(unittest.TestCase):
    def test_immediate_team_win_cannot_be_overridden(self):
        obs=scenario([3,3],[[4],[5]],landlord=0)
        p=fake_policy(True);cards,info=p.choose(obs)
        self.assertEqual(cards,[3,3]);self.assertTrue(info['intervened'])

    def test_landlord_does_not_burn_opening_rocket(self):
        # Reproduces an actual allowed first move with a scattered 20-card hand.
        g=Game(random.Random(12));g.bid(g.turn,3)
        rows,_=evaluate(g.observation(g.turn),6)
        self.assertFalse(any(r['eligible'] and r['move'] and r['move'].kind=='rocket'
                             for r in rows))

    def test_rocket_is_one_remaining_group(self):
        self.assertEqual(shape_cost((16,17)),1)
        self.assertEqual(shape_cost((3,16,17)),2)

    def test_rocket_then_last_combination_is_allowed_and_forced(self):
        obs=scenario([3,3,16,17],[[4],[5]],landlord=0)
        rows,_=evaluate(obs,6)
        self.assertEqual([r['move'].cards for r in rows if r['eligible']],[(16,17)])

    def test_rocket_can_stop_opponent_winning_next_lead(self):
        obs=replace(scenario([3,4,16,17],[[15],[5,6]],target=(13,13),leader=1),passes=1)
        rows,_=evaluate(obs,6)
        self.assertEqual([r['move'].cards for r in rows if r['eligible']],[(16,17)])

    def test_normal_bomb_finish_proof_accounts_for_unknown_controls(self):
        own=[3]*4+[7,7]
        risky=scenario(own,[[4]*4,[5]],landlord=0)
        self.assertFalse(controlled_finish(risky,classify([3]*4)))
        safe=scenario(own,[[16],[17]],landlord=0)
        self.assertTrue(controlled_finish(safe,classify([3]*4)))
        rocket_risk=scenario(own,[[16,17],[5]],landlord=0)
        self.assertFalse(controlled_finish(rocket_risk,classify([3]*4)))

    def test_opening_guard_does_not_force_breaking_all_bombs(self):
        hand=tuple(r for r in range(3,8) for _ in range(4))
        obs=Observation(0,hand,(20,17,17),0,(),None,0,(),hand[:3],'play',((0,3),),3)
        rows,_=evaluate(obs,2)
        self.assertFalse(any(r['reserved'] for r in rows))

    def test_control_cost_is_conditional_not_absolute(self):
        move=classify([16]);target=classify([14])
        intact=control_cost((3,4,16,17),move,target,10)
        no_rocket=control_cost((3,4,16),move,target,10)
        urgent=control_cost((3,4,16,17),move,target,1)
        self.assertGreater(intact,no_rocket)
        self.assertLess(urgent,intact)
        bomb=classify([3]*4)
        hand=tuple([3]*4+[5,7,9])
        self.assertGreater(control_cost(hand,bomb,None,10),control_cost(hand,bomb,target,10))

    def test_pass_is_only_legal_when_following(self):
        for target,leader in [((),None),((5,),1)]:
            obs=scenario([3,3,8],[[6,7],[9,10]],target=target,leader=leader)
            rows,_=evaluate(obs,2)
            self.assertEqual(any(x['move'] is None for x in rows),bool(target))

    def test_farmer_preserves_teammates_winning_lead(self):
        obs=scenario([3,3,4,4,5,5,15],[[6,7,8],[9]],target=(17,),leader=2)
        rows,_=evaluate(obs,6)
        self.assertIsNone(rows[0]['move'])

    def test_block_landlord_last_single(self):
        obs=scenario([4,4,15],[[14],[3,3]],target=(10,),leader=1)
        rows,_=evaluate(obs,8)
        allowed=[r['move'].cards if r['move'] else () for r in rows if r['eligible']]
        self.assertEqual(allowed,[(15,)])

    def test_leading_pair_avoids_giving_last_single_control(self):
        obs=scenario([3,3,4],[[17],[5,6]],landlord=0)
        rows,_=evaluate(obs,8)
        self.assertEqual(rows[0]['move'].cards,(3,3))

    def test_partition_is_not_number_of_cards(self):
        self.assertEqual(exact_turns((3,3,3,4,4,4,5,5)),1)
        self.assertEqual(exact_turns((3,3,4,4,5,5,16)),2)
        self.assertEqual(shape_cost(()),0)

    def test_sampling_conserves_cards_and_public_bottom(self):
        for seed in range(10):
            g=Game(random.Random(seed));g.bid(g.turn,3)
            for seat in range(3):
                obs=g.observation(seat)
                sample=sample_hands(obs,random.Random(seed+90))
                self.assertEqual(tuple(map(len,sample)),obs.counts)
                self.assertEqual(sample[seat],obs.hand)
                self.assertEqual(Counter(sum(sample,())),Counter({**{r:4 for r in range(3,16)},16:1,17:1}))
                self.assertFalse(Counter(obs.bottom)-Counter(sample[g.landlord]))

    def test_model_prompt_and_public_diagnostics_are_separated(self):
        g=Game(random.Random(1));g.bid(g.turn,3);obs=g.observation(g.turn)
        p=fake_policy();cards,info=p.choose(obs)
        self.assertIn(classify(cards),legal_moves(obs.hand))
        self.assertNotIn('candidates',info);self.assertNotIn('prompt',info);self.assertNotIn('hand',info)
        self.assertIn(str(list(obs.hand)),p.agent.calls[0][0])
        self.assertEqual(p.choose(obs)[0],cards)
        a,b=[s for s in range(3) if s!=g.turn]
        # Swap only non-bottom cards so both worlds respect the public deal.
        ca=next(c for c in g.hands[a] if c not in g.bottom);cb=next(c for c in g.hands[b] if c not in g.bottom)
        g.hands[a].remove(ca);g.hands[a].append(cb);g.hands[b].remove(cb);g.hands[b].append(ca)
        self.assertEqual(p.choose(g.observation(g.turn))[0],cards)
        self.assertEqual(p.agent.calls[-1],p.agent.calls[0])

    def test_bad_model_probability_is_rejected(self):
        for probs in [{'x':float('nan')},{'x':0},{'y':1},{'x':-1}]:
            with self.assertRaises(RuntimeError):Policy.probabilities({'answers':{'p':{'probabilities':probs}}},'p',{'x':'OK'})

    def test_model_window_does_not_sacrifice_sampled_team_result(self):
        # Farmer above landlord, after a teammate lead. A model must not trade
        # a whole sampled team win for a nearly equal scalar heuristic score.
        g=Game(random.Random(1003));g.turn=0;g.bid(0,3)
        from ddz.strategy import move_score
        for _ in range(11):
            obs=g.observation(g.turn)
            options=list(legal_moves(obs.hand,g.target))+([None] if g.target else [])
            m=max(options,key=lambda m:move_score(obs.hand,m,obs.seat,obs.landlord,obs.counts,g.leader,g.target))
            g.play(g.turn,g.ids_for(g.turn,m.cards if m else ()))
        rows,_=evaluate(g.observation(g.turn),6)
        best=rows[0]
        for row in rows:
            if row['eligible']:
                self.assertLessEqual(row['risk'],best['risk'])
                self.assertLess(best['sample_value']-row['sample_value'],1/6)

    def test_bidding_never_underbids_or_exceeds_ceiling(self):
        g=Game(random.Random(9));g.bid(g.turn,2);obs=g.observation(g.turn)
        p=fake_policy(True);value,_=p.choose(obs)
        self.assertIn(value,(0,3))
        self.assertNotIn('bottom',p.agent.calls[0][0])


@unittest.skipUnless(os.environ.get('LAYA_TEST_MODEL'),'set LAYA_TEST_MODEL for real GPU validation')
class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.policy=Policy(os.environ['LAYA_TEST_MODEL'],samples=4)

    def test_real_bids_and_play_all_roles(self):
        for seed in range(3):
            g=Game(random.Random(seed));value,_=self.policy.choose(g.observation(g.turn));self.assertIn(value,range(4))
            g.bid(g.turn,3)
            for _ in range(3):
                s=g.turn;obs=g.observation(s);cards,info=self.policy.choose(obs)
                self.assertGreater(info['input_tokens'],0);self.assertLess(info['input_tokens'],1024)
                g.play(s,g.ids_for(s,cards))

    def test_real_model_does_not_open_scattered_hand_with_rocket(self):
        g=Game(random.Random(12));g.bid(g.turn,3)
        cards,_=self.policy.choose(g.observation(g.turn))
        self.assertNotEqual(cards,[16,17])
        self.assertIn(classify(cards),legal_moves(g.observation(g.turn).hand))

    def test_real_prompt_not_truncated(self):
        g=Game(random.Random(73));g.bid(g.turn,3)
        original=self.policy.agent.predict
        def inspect(state,questions):
            items,_=self.policy.agent.prepare(state,questions)
            decoded=self.policy.agent.tok.backend.decode(items[0]['ids'])
            self.assertIn('not true win probabilities',decoded)
            for k,v in questions['play']['criteria'].items():
                self.assertIn(k,decoded)
                self.assertIn(v.split(';')[-1].strip(),decoded)
            return original(state,questions)
        self.policy.agent.predict=inspect
        try:self.policy.choose(g.observation(g.turn))
        finally:self.policy.agent.predict=original

if __name__=='__main__':unittest.main()
