from pathlib import Path
from threading import Event
import tempfile
import unittest
import requests
from casa_watch.server import start_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name)
        (self.root/'index.html').write_text('<h1>Filters</h1>')
        (self.root/'private.txt').write_text('private')
        self.wake=Event()
        self.server=start_server(self.root,self.wake,0)
        self.url=f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.directory.cleanup()

    def test_report_served_private_paths_and_foreign_hosts_rejected(self):
        self.assertEqual(requests.get(self.url,timeout=2).status_code,200)
        self.assertEqual(requests.get(self.url+'/private.txt',timeout=2).status_code,404)
        self.assertEqual(requests.get(self.url,headers={'Host':'evil.example'},timeout=2).status_code,403)

    def test_only_same_origin_can_request_collection(self):
        bad=requests.post(self.url+'/api/collect',json={},headers={'Origin':'https://evil.example'},timeout=2)
        self.assertEqual(bad.status_code,403)
        self.assertFalse(self.wake.is_set())
        good=requests.post(self.url+'/api/collect',json={},headers={'Origin':self.url},timeout=2)
        self.assertEqual(good.status_code,202)
        self.assertTrue(self.wake.is_set())


if __name__=='__main__':
    unittest.main()
