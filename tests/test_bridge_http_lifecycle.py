"""Real loopback transport under fragmented POSTs, with no inference/retries."""
import http.client
import json
import socket
import threading
import time
import unittest
from unittest import mock
from email.message import Message

import test_chat_bridge as fixtures
from test_chat_bridge import b


class ObservedBody:
    """Observe I/O ordering; never supply bytes or synthesize HTTP responses."""
    def __init__(self,stream,events):self.stream=stream;self.events=events
    def __getattr__(self,name):return getattr(self.stream,name)
    def read(self,size=-1):return self.consume(self.stream.read,size)
    def read1(self,size=-1):return self.consume(self.stream.read1,size)
    def consume(self,read,size):
        self.events['reading'].set();self.events['first_action'].set()
        value=read(size);self.events['body_bytes']+=len(value)
        return value


class HttpLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.provider={'type':'codex','timeout_seconds':5,'retries':0}

    def observe(self,bridge):
        events={'first_action':threading.Event(),'reading':threading.Event(),'replying':threading.Event(),'body_bytes':0,'status':None}
        handler=bridge.server.RequestHandlerClass;setup=handler.setup;reply=handler.reply
        def observed_setup(instance):
            setup(instance);instance.rfile=ObservedBody(instance.rfile,events)
        def observed_reply(instance,status,value):
            events['status']=status;events['replying'].set();events['first_action'].set()
            return reply(instance,status,value)
        handler.setup=observed_setup;handler.reply=observed_reply
        return events

    def test_fragmented_rejections_consume_body_before_closing(self):
        for path,key,status,code in [('/v1/other',None,404,'NOT_FOUND'),('/v1/chat/completions','wrong',401,'UNAUTHORIZED')]:
            with self.subTest(status=status):
                client=fixtures.FakeClient()
                with b.ChatBridge(self.provider,client) as bridge:
                    events=self.observe(bridge);body=json.dumps(fixtures.REQUEST).encode()
                    with socket.create_connection(bridge.server.server_address,timeout=3) as connection:
                        connection.sendall(('POST '+path+' HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+
                            (bridge.key if key is None else key)+'\r\nContent-Length: '+str(len(body))+'\r\n\r\n').encode()+body[:1])
                        self.assertTrue(events['first_action'].wait(3),'handler did not enter request processing')
                        # Deterministic old-code failure: it entered reply(401/404)
                        # before ANY body read. This is not a random timing loop.
                        self.assertTrue(events['reading'].is_set(),'final rejection closed a POST with an unread body')
                        self.assertFalse(events['replying'].is_set(),'rejection preceded complete framed body')
                        connection.sendall(body[1:])
                        response=http.client.HTTPResponse(connection);response.begin()
                        self.assertEqual(response.status,status);self.assertEqual(json.loads(response.read())['error']['code'],code)
                        self.assertEqual(events['body_bytes'],len(body))
                        self.assertEqual(response.getheader('Connection'),'close')
                    self.assertFalse(bridge.failed.is_set());self.assertEqual(client.calls,0)
                    address=bridge.server.server_address;listener=bridge.thread
                self.assertFalse(listener.is_alive())
                with socket.socket() as check:self.assertNotEqual(check.connect_ex(address),0)

    def test_rejections_at_size_limit_then_success_have_no_socket_or_worker_leak(self):
        client=fixtures.FakeClient();body=b'x'*b.MAX_REQUEST
        with b.ChatBridge(self.provider,client) as bridge:
            workers=[]
            for path,key,status in [('/v1/other',bridge.key,404),('/v1/chat/completions','wrong',401)]*3:
                connection=http.client.HTTPConnection(*bridge.server.server_address,timeout=4)
                try:
                    connection.request('POST',path,body=body,headers={'Authorization':'Bearer '+key})
                    response=connection.getresponse();self.assertEqual(response.status,status)
                    json.loads(response.read());self.assertEqual(response.getheader('Connection'),'close')
                finally:connection.close()
                workers.extend(list(bridge.server._threads))
            connection=http.client.HTTPConnection(*bridge.server.server_address,timeout=4)
            try:
                connection.request('POST','/v1/chat/completions',body=json.dumps(fixtures.REQUEST),headers={'Authorization':'Bearer '+bridge.key})
                response=connection.getresponse();self.assertEqual(response.status,200);json.loads(response.read())
            finally:connection.close()
            workers.extend(list(bridge.server._threads));listener=bridge.thread
            self.assertFalse(bridge.failed.is_set());self.assertEqual(client.calls,1)
        self.assertFalse(listener.is_alive());self.assertTrue(all(not worker.is_alive() for worker in workers))

    def test_bad_framing_is_rejected_without_model_or_unbounded_body_read(self):
        changes=[('Content-Length: 0\r\n','REQUEST_LIMIT'),
            ('Content-Length: -1\r\n','REQUEST_LIMIT'),('Content-Length: invalid\r\n','REQUEST_LIMIT'),
            ('Content-Length: '+str(b.MAX_REQUEST+1)+'\r\n','REQUEST_LIMIT'),
            ('Content-Length: 10\r\nContent-Length: 10\r\n','REQUEST_LIMIT'),
            ('Content-Length: 10\r\nTransfer-Encoding: chunked\r\n','REQUEST_LIMIT'),
            ('Content-Length: 10\r\nTransfer-Encoding:\r\n','REQUEST_LIMIT')]
        for headers,code in changes:
            with self.subTest(headers=headers),b.ChatBridge(self.provider,fixtures.FakeClient()) as bridge:
                events=self.observe(bridge)
                with socket.create_connection(bridge.server.server_address,timeout=3) as connection:
                    connection.sendall(('POST /v1/other HTTP/1.1\r\nHost: localhost\r\n'+headers+'\r\n').encode())
                    response=http.client.HTTPResponse(connection);response.begin()
                    self.assertEqual(response.status,400);self.assertEqual(json.loads(response.read())['error']['code'],code)
                self.assertFalse(events['reading'].is_set());self.assertFalse(bridge.failed.is_set());self.assertEqual(bridge.client.calls,0)

    def test_incomplete_body_and_read_timeout_fail_without_poisoning_auth_rejections(self):
        for authorized in (False,True):
            for timeout in (False,True):
                with self.subTest(authorized=authorized,timeout=timeout),b.ChatBridge(self.provider,fixtures.FakeClient()) as bridge:
                    with mock.patch.object(b,'HTTP_BODY_TIMEOUT',.2):
                        with socket.create_connection(bridge.server.server_address,timeout=3) as connection:
                            connection.sendall(('POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Length: 20\r\nAuthorization: Bearer '+
                                (bridge.key if authorized else 'wrong')+'\r\n\r\nx').encode())
                            if not timeout:connection.shutdown(socket.SHUT_WR)
                            response=http.client.HTTPResponse(connection);response.begin();self.assertEqual(response.status,400)
                            self.assertEqual(json.loads(response.read())['error']['code'],'HTTP_BODY_TIMEOUT' if timeout else 'INCOMPLETE_REQUEST')
                    self.assertEqual(bridge.failed.is_set(),authorized);self.assertEqual(bridge.client.calls,0)

    def test_body_deadline_is_absolute_and_never_reads_past_content_length(self):
        # Clock/read seams exercise production read_body; real sockets and
        # response framing are covered separately above. No retries occur.
        with b.ChatBridge(self.provider,fixtures.FakeClient()) as bridge:
            cls=bridge.server.RequestHandlerClass;handler=cls.__new__(cls);handler.headers=Message()
            handler.headers['Content-Length']='5';handler.connection=mock.Mock()
            handler.rfile=mock.Mock();handler.rfile.read1.return_value=b'x'
            with mock.patch.object(b.time,'monotonic',side_effect=[0,1,11]):
                with self.assertRaisesRegex(b.BridgeError,'HTTP_BODY_TIMEOUT'):handler.read_body()
            self.assertEqual(handler.rfile.read1.call_count,1)
            handler.rfile=mock.Mock();handler.rfile.read1.side_effect=[b'12',b'345']
            with mock.patch.object(b.time,'monotonic',side_effect=[0,1,2]):self.assertEqual(handler.read_body(),b'12345')
            self.assertEqual(handler.rfile.read1.call_args_list,[mock.call(5),mock.call(3)])
            self.assertEqual(bridge.client.calls,0)


if __name__=='__main__':unittest.main()
