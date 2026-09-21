import http.client
import contextlib
import errno
import io
import json
import threading
import unittest
from unittest.mock import patch
import server as app
from ddz.rules import legal_moves
from server import Server


class StartupTests(unittest.TestCase):
    def test_default_port_collision_opens_browser_on_actual_free_port(self):
        started=[]
        def bind(address, policy):
            # Occupy a dynamic port, then route the preferred port to it.
            port=occupied.server_port if address[1]==8770 else address[1]
            result=Server((address[0],port),policy)
            started.append(result)
            return result
        with Server(('127.0.0.1',0),None) as occupied, \
             patch('sys.argv',['server.py']), \
             patch.object(app.Path,'is_file',return_value=True), \
             patch.object(app,'Server',side_effect=bind), \
             patch.object(app,'Policy') as policy, \
             patch.object(Server,'serve_forever'), \
             patch.object(app.webbrowser,'open') as browser, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            app.main()
            policy.assert_called_once()
            self.assertEqual(len(started),1)
            actual=started[0].server_port
            self.assertNotEqual(actual,occupied.server_port)
            browser.assert_called_once_with(f'http://127.0.0.1:{actual}')
            self.assertIn('已被占用',output.getvalue())
            self.assertIn(f'http://127.0.0.1:{actual}',output.getvalue())
        self.assertEqual(started[0].socket.fileno(),-1)

    def test_explicit_busy_port_exits_clearly_before_model_load(self):
        with Server(('127.0.0.1',0),None) as occupied, \
             patch('sys.argv',['server.py','--port',str(occupied.server_port)]), \
             patch.object(app.Path,'is_file',return_value=True), \
             patch.object(app,'Policy') as policy, \
             patch.object(app.webbrowser,'open') as browser, \
             contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as raised:
                app.main()
            self.assertEqual(raised.exception.code,2)
            self.assertIn('已被占用',error.getvalue())
            policy.assert_not_called()
            browser.assert_not_called()

    def test_other_bind_errors_do_not_trigger_fallback(self):
        with patch('sys.argv',['server.py']), \
             patch.object(app.Path,'is_file',return_value=True), \
             patch.object(app,'Server',side_effect=OSError(errno.EACCES,'denied')) as bind, \
             patch.object(app,'Policy') as policy:
            with self.assertRaises(OSError) as raised:
                app.main()
            self.assertEqual(raised.exception.errno,errno.EACCES)
            bind.assert_called_once()
            policy.assert_not_called()


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
