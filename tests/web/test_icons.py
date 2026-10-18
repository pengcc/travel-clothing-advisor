"""Exact public icon allowlist, MIME types and exposure boundary."""
from http.server import ThreadingHTTPServer
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from web.server import Handler, ROOT


class IconRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_all_committed_icons_have_exact_bytes_and_mime(self):
        icons = list((ROOT / 'static/icons/warmth').glob('*/*'))
        self.assertEqual(len(icons), 40)
        for icon in icons:
            with self.subTest(icon=icon.name), urlopen(self.base + '/static/' + str(icon.relative_to(ROOT / 'static'))) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/' + icon.suffix[1:])
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(response.read(), icon.read_bytes())

    def test_unlisted_paths_and_traversal_are_not_exposed(self):
        for path in ['1x/warmth-l0.png', '3x/warmth-l1.png', '1x/warmth-l1.svg',
                     '1x/unknown.png', '../app.js', '1x/../../../../server.py',
                     '%2e%2e/server.py', '1x/warmth-l1.png/extra']:
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                urlopen(self.base + '/static/icons/warmth/' + path)
            self.assertEqual(caught.exception.code, 404)
