import random
import unittest
from collections import Counter
from ddz.game import Game
from ddz.rules import legal_moves, ranks, rank
from ddz.strategy import move_score


class GameTests(unittest.TestCase):
    def game(self):return Game(random.Random(41))
    def test_deal_and_hidden_view(self):
        g=self.game()
        self.assertEqual([len(h) for h in g.hands],[17]*3)
        self.assertEqual(sorted(sum(g.hands,[])+g.bottom),list(range(54)))
        self.assertEqual(g.view()['bottom'],[])
        self.assertIsNone(g.view()['revealed'])
        self.assertNotIn('hands',g.view())
        self.assertEqual(g.observation(1).hand,ranks(g.hands[1]))
        self.assertEqual(g.observation(1).bottom,())

    def test_dealing_uses_shuffle_positions_without_strength_balancing(self):
        class FixedShuffle:
            calls=0
            def shuffle(self,deck):
                self.calls+=1
                # Deliberately strong first seat: both jokers and three quads.
                first=[52,53]+list(range(12))+[48,49,50]
                deck[:]=first+[c for c in range(54) if c not in first]
                self.dealt=deck.copy()
            def randrange(self,n):return 2
        rng=FixedShuffle();g=Game(rng)
        self.assertEqual(rng.calls,1)
        for seat in range(3):
            self.assertEqual(set(g.hands[seat]),set(rng.dealt[seat*17:(seat+1)*17]))
        self.assertEqual(g.bottom,rng.dealt[51:])
        self.assertTrue({52,53}<=set(g.hands[0]))
        g.deal()
        self.assertEqual(rng.calls,2)  # Exactly one shuffle per requested deal.

    def test_bid_raise_three_and_bottom(self):
        g=self.game();s=g.turn
        g.bid(s,1)
        for bad in [1,-1,4,True,1.5,None]:
            with self.assertRaises(ValueError):g.bid(g.turn,bad)
        g.bid(g.turn,3)
        self.assertEqual(g.phase,'play');self.assertEqual(g.turn,g.landlord)
        self.assertEqual(len(g.hands[g.landlord]),20)
        self.assertEqual(g.view()['bottom'],g.bottom)
        self.assertEqual(g.high_bid,3)

    def test_all_pass_rotates_start_and_clears(self):
        g=self.game();start=g.turn
        for _ in range(3):g.bid(g.turn,0)
        self.assertEqual(g.phase,'bid');self.assertEqual(g.round,2)
        self.assertEqual(g.turn,(start+1)%3);self.assertEqual(g.version,3)
        self.assertEqual(g.bids,[]);self.assertEqual(g.history,[])

    def test_two_passes_restore_lead(self):
        g=self.game();g.bid(g.turn,3);s=g.turn
        with self.assertRaises(ValueError):g.play(s,[])
        g.play(s,[g.hands[s][0]])
        g.play(g.turn,[]);g.play(g.turn,[])
        self.assertEqual(g.turn,s);self.assertIsNone(g.target)
        with self.assertRaises(ValueError):g.play(g.turn,[])

    def test_invalid_play_is_atomic(self):
        g=self.game();g.bid(g.turn,3);s=g.turn;before=repr(g.view())
        for cards in [None,[True],[g.hands[s][0]]*2,[g.hands[(s+1)%3][0]]]:
            with self.assertRaises(ValueError):g.play(s,cards)
            self.assertEqual(repr(g.view()),before)
        with self.assertRaises(ValueError):g.play((s+1)%3,[])
        self.assertEqual(repr(g.view()),before)

    def test_spring_and_antispring_zero_sum(self):
        for landlord_won,plays,spring in [(True,[1,0,0],'春天'),(False,[1,1,0],'反春天'),(True,[2,1,0],None),(False,[2,1,0],None)]:
            g=self.game();g.landlord=0;g.high_bid=2;g.bombs=2;g.play_counts=plays
            g.finish(0 if landlord_won else 1)
            self.assertEqual(g.settlement['spring'],spring)
            self.assertEqual(g.settlement['multiplier'],8 if spring else 4)
            self.assertEqual(sum(g.settlement['delta']),0)
            self.assertEqual(abs(g.settlement['delta'][0]),abs(g.settlement['delta'][1])*2)
            self.assertEqual(g.phase,'over')

    def test_farmer_finishes_entire_team(self):
        g=self.game();g.phase='play';g.landlord=0;g.high_bid=1;g.turn=1;g.hands=[[4,8],[0],[12]]
        g.play(1,[0])
        self.assertEqual(g.winner,1);self.assertFalse(g.settlement['landlord_won'])
        self.assertGreater(g.scores[2],0)
        with self.assertRaises(ValueError):g.play(2,[12])

    def test_hidden_swap_does_not_change_observation(self):
        g=self.game();g.bid(g.turn,3);seat=g.landlord
        before=g.observation(seat)
        a,b=[s for s in range(3) if s!=seat]
        g.hands[a][0],g.hands[b][0]=g.hands[b][0],g.hands[a][0]
        self.assertEqual(g.observation(seat),before)

    def test_seeded_complete_games_conserve_cards_and_terminate(self):
        for seed in range(40):
            g=Game(random.Random(seed));g.bid(g.turn,1);g.bid(g.turn,0);g.bid(g.turn,0)
            for ply in range(180):
                s=g.turn;hand=ranks(g.hands[s]);options=list(legal_moves(hand,g.target))
                if g.target:options.append(None)
                move=max(options,key=lambda m:move_score(hand,m,s,g.landlord,list(map(len,g.hands)),g.leader,g.target))
                g.play(s,g.ids_for(s,move.cards if move else ()))
                accounted=Counter(r for h in g.hands for r in ranks(h))+Counter(r for _,cs in g.history for r in cs)
                self.assertEqual(accounted,Counter({**{r:4 for r in range(3,16)},16:1,17:1}))
                if g.phase=='over':break
            self.assertEqual(g.phase,'over',f'seed={seed}')
            self.assertEqual(sum(g.scores),0)

if __name__=='__main__':unittest.main()
