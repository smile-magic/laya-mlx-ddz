"""Reproducible finite evaluation; prints results, saves no game or model data."""
import argparse
import json
from pathlib import Path
import random
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ddz.game import Game
from ddz.rules import legal_moves, ranks
from ddz.strategy import Policy, evaluate, move_score, allies


def play(seed, seats, policy):
    game=Game(random.Random(seed));game.turn=0;game.bid(0,3)
    latencies=[];interventions=0;calls=0;tokens=[]
    for ply in range(180):
        seat=game.turn;obs=game.observation(seat)
        if seat in seats:
            if policy:
                cards,info=policy.choose(obs);latencies.append(info['total_ms'])
                tokens.append(info.get('input_tokens',0));interventions+=info['intervened'];calls+=1
            else:
                rows,_=evaluate(obs,6);m=rows[0]['move'];cards=m.cards if m else ()
        else:
            hand=ranks(game.hands[seat]);options=list(legal_moves(hand,game.target))
            if game.target:options.append(None)
            m=max(options,key=lambda m:move_score(hand,m,seat,game.landlord,obs.counts,game.leader,game.target))
            cards=m.cards if m else ()
        game.play(seat,game.ids_for(seat,cards))
        if game.phase=='over':
            return {'winner':game.winner,'plies':ply+1,'calls':calls,'interventions':interventions,
                    'latencies':latencies,'tokens':tokens}
    raise AssertionError(f'Unfinished round seed={seed}, seats={seats}')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path)
    p.add_argument('--seeds',type=int,default=6);p.add_argument('--start-seed',type=int,default=100)
    p.add_argument('--mode',choices=['roles','table'],default='roles');args=p.parse_args()
    policy=Policy(args.model) if args.model else None
    total=[];roles={}
    for seed in range(args.start_seed,args.start_seed+args.seeds):
        baseline=play(seed,[],None)
        for seats in ([0],[1],[2]) if args.mode=='roles' else ([1,2],):
            row=play(seed,seats,policy);perspective=seats[0]
            row['win']=allies(row['winner'],perspective,0)
            row['baseline_win']=allies(baseline['winner'],perspective,0)
            row['seat']=str(seats);total.append(row)
            print(json.dumps({'seed':seed,'seats':seats,**{k:v for k,v in row.items() if k not in ('latencies','tokens','seat')}},ensure_ascii=False),flush=True)
    for row in total:
        r=roles.setdefault(row['seat'],{'games':0,'wins':0,'baseline_wins':0})
        r['games']+=1;r['wins']+=row['win'];r['baseline_wins']+=row['baseline_win']
    latency=[x for r in total for x in r['latencies']];tokens=[x for r in total for x in r['tokens']]
    print(json.dumps({'summary':roles,'games':len(total),'calls':sum(r['calls'] for r in total),
                      'interventions':sum(r['interventions'] for r in total),
                      'average_ms':round(statistics.mean(latency),1) if latency else None,
                      'max_ms':max(latency,default=None),'max_tokens':max(tokens,default=None)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
