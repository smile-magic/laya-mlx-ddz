import itertools
import random
import unittest
from collections import Counter
from ddz.rules import classify, beats, legal_moves, all_moves, rank, ranks


class RulesTests(unittest.TestCase):
    def test_all_kinds(self):
        examples=[([3],'single'),([4,4],'pair'),([5]*3,'triple'),([6]*3+[7],'triple_single'),
                  ([6]*3+[7]*2,'triple_pair'),(list(range(3,8)),'straight'),
                  ([3,3,4,4,5,5],'pairs'),([3]*3+[4]*3,'plane'),
                  ([3]*3+[4]*3+[5]*2,'plane_single'),([3]*3+[4]*3+[5]*2+[6]*2,'plane_pair'),
                  ([7]*4+[8]*2,'four_single'),([7]*4+[8]*2+[9]*2,'four_pair'),
                  ([15]*4,'bomb'),([16,17],'rocket')]
        for cards,kind in examples:
            with self.subTest(kind=kind):self.assertEqual(classify(cards).kind,kind)

    def test_invalid_combinations(self):
        for cards in [[],[3,4],[3]*5,[16]*2,[3,4,5,6],[11,12,13,14,15],
                      [14]*3+[15]*3,[3]*4+[4]*4,[3]*3+[4]*3+[16,17],
                      [3]*4+[16,17],[3]*4+[4]*4+[5]*2,[3]*3+[4]*3+[5]*3+[6],
                      [2],[18],[True],[3.0]]:
            with self.subTest(cards=cards):self.assertIsNone(classify(cards))

    def test_plane_repeated_single_wings(self):
        self.assertEqual(classify([3]*3+[4]*3+[5]*3+[8]*3).kind,'plane_single')
        self.assertEqual(classify([3]*3+[4]*3+[5]*3+[6]*3+[9]*4).kind,'plane_single')
        self.assertEqual(classify([3]*3+[4]*3+[5]*3+[6]*3).kind,'plane')

    def test_comparison_uses_body_and_length(self):
        self.assertTrue(beats(classify([4]*3+[5]*3+[6,7]),classify([3]*3+[4]*3+[15,16])))
        self.assertFalse(beats(classify([8]*3+[9]*3+[3]*2+[4]*2),classify([3]*3+[4]*3+[7,8])))
        self.assertFalse(beats(classify(list(range(4,10))),classify(list(range(3,8)))))
        self.assertTrue(beats(classify([3]*4),classify([15]*3+[16])))
        self.assertFalse(beats(classify([15]*4+[3,4]),classify([3]*4)))
        self.assertTrue(beats(classify([16,17]),classify([15]*4)))
        self.assertFalse(beats(classify([16,17]),classify([16,17])))

    def test_full_deck_mapping(self):
        counts=Counter(rank(c) for c in range(54))
        self.assertEqual(counts,Counter({**{r:4 for r in range(3,16)},16:1,17:1}))
        for bad in [-1,54,True,'1']:
            with self.assertRaises(ValueError):rank(bad)

    def test_generator_canonical_legal_and_subset(self):
        rng=random.Random(718)
        for _ in range(35):
            hand=ranks(rng.sample(range(54),20))
            moves=all_moves(hand)
            self.assertEqual(len(moves),len({m.cards for m in moves}))
            for m in moves:
                self.assertFalse(Counter(m.cards)-Counter(hand))
                self.assertEqual(classify(m.cards),m)
            target=rng.choice(moves)
            self.assertEqual(legal_moves(hand,target),tuple(m for m in moves if beats(m,target)))

    def test_small_hand_generation_exhaustive_independent_oracle(self):
        def oracle(cs):
            c=Counter(cs);n=len(cs);v=sorted(c.values());rs=sorted(c)
            consecutive=rs[-1]<=14 and rs==list(range(rs[0],rs[-1]+1))
            if n==1 or cs==(16,17):return True
            if len(c)==1 and n<=4:return True
            if v in ([1,3],[2,3]):return True
            if consecutive and ((v==[1]*n and n>=5) or (v==[2]*len(c) and len(c)>=3) or (v==[3]*len(c) and len(c)>=2)):return True
            for r in c:
                if c[r]==4:
                    rem=c.copy();del rem[r]
                    if n==6 and not(16 in rem and 17 in rem):return True
                    if n==8 and sorted(rem.values())==[2,2]:return True
            for start in range(3,14):
                for size in range(2,6):
                    body=range(start,start+size)
                    if start+size-1>14 or any(c[r]!=3 for r in body):continue
                    rem=Counter({r:x for r,x in c.items() if r not in body})
                    if n==size*4 and sum(rem.values())==size and not(16 in rem and 17 in rem):return True
                    if n==size*5 and len(rem)==size and all(x==2 for x in rem.values()):return True
            return False
        hands=[(3,3,3,4,4,4,5,5,6,6),(3,3,3,3,4,4,5,5,16,17),(3,4,5,6,7,8,9,14,15,17)]
        for hand in hands:
            expected={cs for n in range(1,len(hand)+1) for cs in set(itertools.combinations(hand,n)) if oracle(cs)}
            self.assertEqual({m.cards for m in all_moves(hand)},expected)

if __name__=='__main__':unittest.main()
