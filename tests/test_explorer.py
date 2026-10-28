import http.client, json, os, stat, sys, tempfile, threading, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import explorer


def write(path, data=b'', mode=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data if isinstance(data, bytes) else data.encode())
    if mode is not None:
        os.chmod(path, mode)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        write(self.root + '/notes.txt', 'line one\nneedle in a haystack\n')
        write(self.root + '/.hidden', 'secret')
        write(self.root + '/my file.txt', 'spaces in name')
        write(self.root + '/bin.dat', b'\x7fELF\x00\x01\x02binary')
        write(self.root + '/sub/deep/target-log.txt', 'inside deep needle')
        write(self.root + "/we'ird\"name$(x).txt", 'quotes')
        write(self.root + '/-rf', 'a file named like a flag')

    def tearDown(self):
        self.tmp.cleanup()


class Permissions(unittest.TestCase):
    def test_plain_english(self):
        p = explorer.explain_mode(0o100754, False)
        self.assertEqual(p['owner'], 'read it, change it, run it')
        self.assertEqual(p['group'], 'read it, run it')
        self.assertEqual(p['everyone'], 'read it')
        self.assertEqual(p['flags'], [])

    def test_folder_wording_and_nothing(self):
        p = explorer.explain_mode(0o040700, True)
        self.assertEqual(p['owner'], 'list its contents, add or remove files, enter it')
        self.assertEqual(p['everyone'], 'nothing')

    def test_security_flags(self):
        self.assertTrue(any('Anyone' in f for f in explorer.explain_mode(0o100666, False)['flags']))
        self.assertTrue(any('SUID' in f for f in explorer.explain_mode(0o104755, False)['flags']))
        tmpdir = explorer.explain_mode(0o041777, True)['flags']
        self.assertTrue(any('Sticky' in f for f in tmpdir))
        self.assertFalse(any('Anyone' in f for f in tmpdir), '/tmp style folders are normal, not alarming')


class Paths(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(explorer.clean('~'), str(Path.home()))
        self.assertEqual(explorer.clean('/etc/../etc/./ssh/'), '/etc/ssh')
        self.assertEqual(explorer.clean('Projects'), str(Path.home() / 'Projects'))
        for bad in ('a\x00b', 'x' * 5000, None, 5):
            with self.assertRaises(ValueError):
                explorer.clean(bad)


class Listing(Fixture):
    def test_hidden_toggle_and_order(self):
        shown = explorer.list_dir(self.root, False)
        names = [e['name'] for e in shown['entries']]
        self.assertNotIn('.hidden', names)
        self.assertEqual(shown['hidden_count'], 1)
        self.assertIn('.hidden', [e['name'] for e in explorer.list_dir(self.root, True)['entries']])
        self.assertEqual(explorer.list_dir(self.root, False)['command'], 'ls -l ' + explorer.q(self.root))
        self.assertTrue(explorer.list_dir(self.root, True)['command'].startswith('ls -la '))

    def test_hostile_names_are_data_and_commands_are_quoted(self):
        entries = {e['name']: e for e in explorer.list_dir(self.root, False)['entries']}
        self.assertIn("we'ird\"name$(x).txt", entries)
        self.assertEqual(entries['sub']['type'], 'dir')
        self.assertTrue(explorer.list_dir(self.root + '/sub', False)['parent'], self.root)
        import shlex
        cmd = explorer.list_dir(self.root, False)['cd']
        self.assertEqual(shlex.split(cmd), ['cd', self.root])

    def test_errors_are_friendly(self):
        with self.assertRaises(FileNotFoundError):
            explorer.list_dir(self.root + '/nope', False)
        if os.geteuid() != 0:
            os.chmod(self.root + '/sub', 0)
            try:
                with self.assertRaises(PermissionError) as ctx:
                    explorer.list_dir(self.root + '/sub', False)
                self.assertIn('sudo', str(ctx.exception))
            finally:
                os.chmod(self.root + '/sub', 0o755)

    def test_symlink_shown_as_link_with_target(self):
        os.symlink(self.root + '/notes.txt', self.root + '/shortcut')
        entry = next(e for e in explorer.list_dir(self.root, False)['entries'] if e['name'] == 'shortcut')
        self.assertEqual(entry['type'], 'link')
        self.assertEqual(entry['link'], self.root + '/notes.txt')


class Preview(Fixture):
    def test_text(self):
        data = explorer.preview(self.root + '/notes.txt')
        self.assertEqual(data['kind'], 'text')
        self.assertIn('needle in a haystack', data['text'])
        self.assertEqual(data['command'], 'head -n 200 ' + explorer.q(self.root + '/notes.txt'))

    def test_binary_shows_hex_not_garbage(self):
        data = explorer.preview(self.root + '/bin.dat')
        self.assertEqual(data['kind'], 'binary')
        self.assertTrue(data['text'].startswith('00000000  7f 45 4c 46'))
        self.assertIn('magic bytes', data['note'])

    def test_large_file_is_capped(self):
        write(self.root + '/big.txt', 'x\n' * 500000)
        data = explorer.preview(self.root + '/big.txt')
        self.assertLessEqual(len(data['text'].splitlines()), 200)
        self.assertTrue(data['truncated'])

    def test_errors(self):
        with self.assertRaises(IsADirectoryError):
            explorer.preview(self.root + '/sub')
        with self.assertRaises(FileNotFoundError):
            explorer.preview(self.root + '/missing.txt')


class Search(Fixture):
    def paths(self, result):
        return sorted(os.path.relpath(r['path'], self.root) for r in result['results'])

    def test_name_search_plain_and_glob(self):
        self.assertEqual(self.paths(explorer.search(self.root, 'target-log', 'name')), ['sub/deep/target-log.txt'])
        self.assertEqual(self.paths(explorer.search(self.root, '*.dat', 'name')), ['bin.dat'])
        self.assertEqual(self.paths(explorer.search(self.root, 'DEEP', 'name')), ['sub/deep'], 'case-insensitive')
        self.assertEqual(explorer.search(self.root, 'zzz', 'name')['results'], [])

    def test_content_search_finds_lines(self):
        result = explorer.search(self.root, 'needle', 'content')
        found = {(os.path.relpath(r['path'], self.root), r['line']) for r in result['results']}
        self.assertIn(('notes.txt', 2), found)
        self.assertIn(('sub/deep/target-log.txt', 1), found)
        self.assertTrue(result['command'].startswith('grep -rInF'))

    def test_search_text_is_never_treated_as_a_flag_or_pattern(self):
        self.assertEqual(self.paths(explorer.search(self.root, '-rf', 'name')), ['-rf'])
        self.assertEqual(explorer.search(self.root, '--help', 'content')['results'], [])
        self.assertEqual(explorer.search(self.root, '.*', 'content')['results'], [], 'regex characters are matched literally')
        self.assertEqual(explorer.search(self.root, '$(touch pwned)', 'content')['results'], [])
        self.assertFalse(os.path.exists('pwned'))

    def test_validation(self):
        for bad in ('', '   ', 'x' * 201):
            with self.assertRaises(ValueError):
                explorer.search(self.root, bad, 'name')
        with self.assertRaises(FileNotFoundError):
            explorer.search(self.root + '/nowhere', 'a', 'name')

    def test_results_are_capped(self):
        for i in range(explorer.MAX_RESULTS + 40):
            write(self.root + '/many/file%03d.cap' % i)
        result = explorer.search(self.root, '.cap', 'name')
        self.assertEqual(len(result['results']), explorer.MAX_RESULTS)
        self.assertTrue(result['limited'])


class Server(Fixture):
    def setUp(self):
        super().setUp()
        self.server = explorer.make_server(0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        super().tearDown()

    def call(self, path, method='GET', host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader('Host', host or '127.0.0.1:%d' % self.port)
        conn.endheaders()
        res = conn.getresponse(); body = res.read(); conn.close()
        return res, body

    def test_listing_over_http_and_security_headers(self):
        res, body = self.call('/api/list?path=' + self.root)
        self.assertEqual(res.status, 200)
        self.assertIn('notes.txt', [e['name'] for e in json.loads(body)['entries']])
        self.assertIn("default-src 'none'", res.getheader('Content-Security-Policy'))
        self.assertEqual(res.getheader('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.getheader('Cache-Control'), 'no-store')

    def test_only_this_computer_and_this_app_can_ask(self):
        for host in ('evil.example', 'evil.example:%d' % self.port, '10.0.0.5:%d' % self.port, 'localhost:1'):
            self.assertEqual(self.call('/api/list?path=/etc', host=host)[0].status, 403, host)
        self.assertEqual(self.call('/api/list?path=/etc', host='localhost:%d' % self.port)[0].status, 200)

    def test_read_only(self):
        for method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            self.assertEqual(self.call('/api/list?path=' + self.root, method=method)[0].status, 405, method)
        self.assertTrue(os.path.exists(self.root + '/notes.txt'))

    def test_errors_use_proper_status_and_never_leak_traces(self):
        self.assertEqual(self.call('/api/list?path=' + self.root + '/nope')[0].status, 404)
        res, body = self.call('/api/list?path=a%00b')
        self.assertEqual(res.status, 400)
        self.assertNotIn(b'Traceback', body)
        self.assertEqual(self.call('/api/unknown')[0].status, 404)
        self.assertEqual(self.call('/api/search?q=')[0].status, 400)

    def test_assets_and_health(self):
        for path, kind in (('/', 'text/html'), ('/app.js', 'text/javascript'), ('/style.css', 'text/css')):
            res, body = self.call(path)
            self.assertEqual(res.status, 200, path)
            self.assertTrue(res.getheader('Content-Type').startswith(kind))
            self.assertGreater(len(body), 100)
        self.assertTrue(json.loads(self.call('/api/health')[1])['ok'])

    def test_frontend_never_uses_innerhtml(self):
        js = (Path(explorer.HERE) / 'static' / 'app.js').read_text()
        for banned in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval('):
            self.assertNotIn(banned, js)


class Places(unittest.TestCase):
    def test_only_existing_folders_with_explanations(self):
        found = explorer.places()
        self.assertTrue(found)
        for place in found:
            self.assertTrue(os.path.isdir(place['path']))
            self.assertTrue(place['why'] and place['command'].startswith('cd '))
        self.assertIn('/var/log', [p['path'] for p in found])


if __name__ == '__main__':
    unittest.main()
