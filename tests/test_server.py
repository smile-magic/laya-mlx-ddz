import http.client
import json
import threading
import unittest
from ddz.rules import legal_moves
from server import Server


class StubPolicy:
    fail=False
    def choose(self,obs):
        if self.fail:raise RuntimeError('simulated model failure')
        if obs.phase=='bid':return 3,{'seat':obs.seat,'model':True}
        options=legal_moves(obs.hand,__import__('ddz.rules',fromlist=['classify']).classify(obs.target))
        return list(options[0].cards) if options else [],{'seat':obs.seat,'model':True}


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=StubPolicy();cls.server=Server(('127.0.0.1',0),cls.policy)
        cls.thread=threading.Thread(target=cls.server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
        cls.server.sessions.clear()

    def post(self,path,body,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            connection.request('POST','/api/'+path,json.dumps(body),headers or {'Content-Type':'application/json'})
            response=connection.getresponse();return response.status,json.loads(response.read())
        finally:connection.close()

    def new(self):
        status,data=self.post('new',{});self.assertEqual(status,200)
        return data['id'],self.server.sessions[data['id']].game

    def test_origin_rejection(self):
        status,_=self.post('new',{}, {'Origin':'https://example.com'})
        self.assertEqual(status,403)

    def test_stale_version_cannot_double_bid(self):
        key,g=self.new();g.turn=0;version=g.version
        status,_=self.post('bid',{'id':key,'version':version,'bid':1});self.assertEqual(status,200)
        status,_=self.post('bid',{'id':key,'version':version,'bid':3});self.assertEqual(status,409)
        self.assertEqual(g.bids,[(0,1)])

    def test_failure_keeps_turn_and_retry(self):
        key,g=self.new();g.turn=1;before=repr(g.view());self.policy.fail=True
        try:
            status,data=self.post('step',{'id':key,'version':g.version})
            self.assertEqual(status,500);self.assertEqual(repr(g.view()),before)
        finally:self.policy.fail=False
        status,data=self.post('step',{'id':key,'version':g.version})
        self.assertEqual(status,200);self.assertEqual(g.landlord,1)

    def test_busy_model_does_not_mutate_game(self):
        key,g=self.new();g.turn=1;before=repr(g.view());self.server.gpu_lock.acquire()
        try:
            status,_=self.post('step',{'id':key,'version':g.version});self.assertEqual(status,429)
        finally:self.server.gpu_lock.release()
        self.assertEqual(repr(g.view()),before)

    def test_view_has_no_hidden_hands_or_sampling(self):
        key,g=self.new();g.turn=0;g.bid(0,3)
        g.last_ai={'seat':1,'reason':'策略选择','legal_count':99,'input_tokens':500,
                   'candidates':[[16,17]],'prompt':'private'}
        status,data=self.post('state',{'id':key});self.assertEqual(status,200)
        self.assertIsNone(data['game']['revealed'])
        self.assertNotIn('hands',data['game']);self.assertNotIn('seed',data['game'])
        self.assertEqual(data['game']['hand'],g.hands[0])
        self.assertNotIn('candidates',data['game'])
        self.assertEqual(data['game']['last_ai'],{'seat':1,'reason':'策略选择'})

    def test_human_cannot_play_other_seat(self):
        key,g=self.new();g.turn=1;g.bid(1,3);before=repr(g.view())
        status,_=self.post('play',{'id':key,'version':g.version,'seat':1,'cards':[g.hands[1][0]]})
        self.assertEqual(status,400);self.assertEqual(repr(g.view()),before)

    def test_next_round_preserves_scores_and_resets_private_round(self):
        key,g=self.new();g.scores=[4,-2,-2];version=g.version
        status,data=self.post('next',{'id':key,'version':version})
        self.assertEqual(status,200);self.assertEqual(g.scores,[4,-2,-2]);self.assertEqual(g.version,version+1)
        self.assertEqual(data['game']['bottom'],[]);self.assertEqual(data['game']['history'],[])

if __name__=='__main__':unittest.main()
