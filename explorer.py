#!/usr/bin/env python3
"""Linux Explorer: a read-only file and directory browser that teaches the commands behind every click.

Runs only on this computer (127.0.0.1), uses only the Python standard library, and never changes,
deletes or uploads anything.
"""
import json, os, re, shlex, socket, stat, subprocess, sys, threading, time, webbrowser
from datetime import datetime
from fnmatch import fnmatch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get('LINUX_EXPLORER_PORT', '8765'))
SKIP_WALK = {'/proc', '/sys', '/dev', '/run'}          # virtual folders: huge and slow to search
MAX_LIST, MAX_RESULTS, SEARCH_SECONDS, PREVIEW_BYTES = 5000, 200, 6, 64 * 1024

# Folders worth knowing, with the reason a security analyst cares.
PLACES = [
    ('~', 'Home', 'Your files. Hidden settings start with a dot, like .bashrc and .ssh.'),
    ('/var/log', 'Logs', 'Where the system writes what happened. A SOC analyst lives here: auth.log, syslog, web server logs.'),
    ('/etc', 'Configuration', 'System settings: users (passwd), services, SSH, cron jobs. Attackers change these to stay in.'),
    ('/tmp', 'Temporary files', 'Anyone can write here. Malware often drops files here, so unusual files are worth a look.'),
    ('/usr/bin', 'Programs', 'Most commands you run live here. A normal command in the wrong folder is suspicious.'),
    ('/home', 'All users', 'One folder per person. Look for accounts that should not exist.'),
    ('/opt', 'Extra software', 'Third-party tools installed outside the package manager.'),
    ('/proc', 'Running processes (virtual)', 'Not real files: a live view of the kernel and every process. ls /proc shows process IDs.'),
    ('/root', 'Administrator home', 'The root user. Needs sudo to open.'),
    ('~/linux-lab/sandbox', 'Practice area', 'Safe practice files from your Linux lab.'),
    ('~/Projects', 'Your projects', 'Your code.'),
]


def clean(path):
    """Normalize a user-supplied path; reject anything that is not a plain filesystem path."""
    if not isinstance(path, str) or '\x00' in path or len(path) > 4096:
        raise ValueError('That is not a valid path.')
    expanded = os.path.expanduser(path or '~')
    if not os.path.isabs(expanded):
        expanded = os.path.join(str(Path.home()), expanded)
    return os.path.normpath(expanded)


def q(text):
    return shlex.quote(text)


def explain_mode(mode, is_dir):
    """Plain-English meaning of rwx permissions, plus security flags."""
    verbs = ('list its contents', 'add or remove files', 'enter it') if is_dir else ('read it', 'change it', 'run it')
    def who(shift):
        bits = (mode >> shift) & 7
        have = [verbs[i] for i, bit in enumerate((4, 2, 1)) if bits & bit]
        return ', '.join(have) if have else 'nothing'
    flags = []
    if mode & stat.S_IWOTH and not (is_dir and mode & stat.S_ISVTX):
        flags.append('Anyone on the system can change this. Worth noticing in a security review.')
    if mode & stat.S_ISUID:
        flags.append('SUID: runs with its owner\'s power, often root. Attackers look for these.')
    if mode & stat.S_ISGID and not is_dir:
        flags.append('SGID: runs with its group\'s power.')
    if is_dir and mode & stat.S_ISVTX:
        flags.append('Sticky bit: people can only delete their own files here (normal for /tmp).')
    return {'owner': who(6), 'group': who(3), 'everyone': who(0), 'flags': flags}


def entry_info(parent, name):
    full = os.path.join(parent, name)
    try:
        st = os.lstat(full)
    except OSError:
        return {'name': name, 'type': 'unknown', 'size': 0, 'mode': '??????????', 'owner': '?', 'group': '?', 'mtime': 0, 'flags': [], 'perm': None}
    is_link = stat.S_ISLNK(st.st_mode)
    target = None
    kind = 'link' if is_link else 'dir' if stat.S_ISDIR(st.st_mode) else 'file' if stat.S_ISREG(st.st_mode) else 'special'
    if is_link:
        try:
            target = os.readlink(full)
            kind = 'dir' if os.path.isdir(full) else 'link'
        except OSError:
            pass
    try:
        import pwd, grp
        owner, group = pwd.getpwuid(st.st_uid).pw_name, grp.getgrgid(st.st_gid).gr_name
    except Exception:
        owner, group = str(st.st_uid), str(st.st_gid)
    perm = explain_mode(st.st_mode, kind == 'dir')
    return {'name': name, 'type': kind, 'link': target, 'size': st.st_size, 'mode': stat.filemode(st.st_mode), 'owner': owner,
            'group': group, 'mtime': int(st.st_mtime), 'flags': perm['flags'], 'perm': perm}


def list_dir(path, show_hidden):
    path = clean(path)
    if not os.path.isdir(path):
        raise FileNotFoundError('That folder does not exist.')
    try:
        names = sorted(os.listdir(path), key=str.lower)
    except PermissionError:
        raise PermissionError('You do not have permission to open this folder. In a terminal, `sudo ls %s` would show it.' % q(path))
    hidden = sum(1 for n in names if n.startswith('.'))
    if not show_hidden:
        names = [n for n in names if not n.startswith('.')]
    truncated = len(names) > MAX_LIST
    entries = [entry_info(path, n) for n in names[:MAX_LIST]]
    parent = os.path.dirname(path) if path != '/' else None
    return {'path': path, 'parent': parent, 'entries': entries, 'hidden_count': hidden, 'truncated': truncated,
            'command': ('ls -la %s' if show_hidden else 'ls -l %s') % q(path), 'cd': 'cd %s' % q(path)}


def hexdump(data):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        lines.append('%08x  %-47s  %s' % (i, ' '.join('%02x' % b for b in chunk), ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)))
    return '\n'.join(lines)


def preview(path):
    path = clean(path)
    info = entry_info(os.path.dirname(path), os.path.basename(path))
    if info['type'] == 'dir':
        raise IsADirectoryError('That is a folder. Click it to open it.')
    if not os.path.exists(path):
        raise FileNotFoundError('That file does not exist.')
    try:
        with open(path, 'rb') as handle:
            data = handle.read(PREVIEW_BYTES)
    except PermissionError:
        raise PermissionError('You do not have permission to read this file. In a terminal, `sudo cat %s` would.' % q(path))
    except OSError as error:
        raise OSError('Could not read this file (%s).' % error.strerror)
    try:
        described = subprocess.run(['file', '-b', '--', path], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        described = ''
    binary = b'\x00' in data[:8192]
    if binary:
        return {'path': path, 'info': info, 'kind': 'binary', 'description': described, 'text': hexdump(data[:256]),
                'command': 'file %s && xxd %s | head' % (q(path), q(path)),
                'note': 'This is not a text file. The first bytes ("magic bytes") tell programs what it is: 7f 45 4c 46 is a Linux program, 50 4b is a zip.'}
    text = data.decode('utf-8', errors='replace')
    lines = text.splitlines()[:200]
    return {'path': path, 'info': info, 'kind': 'text', 'description': described, 'text': '\n'.join(lines),
            'truncated': len(data) >= PREVIEW_BYTES or len(text.splitlines()) > 200, 'command': 'head -n 200 %s' % q(path)}


def search(root, query, mode):
    root = clean(root)
    query = (query or '').strip()
    if not os.path.isdir(root):
        raise FileNotFoundError('Search folder does not exist.')
    if not query or len(query) > 200:
        raise ValueError('Type something to search for (up to 200 characters).')
    if mode == 'content':
        command = 'grep -rInF --max-count=2 -- %s %s' % (q(query), q(root))
        args = ['grep', '-rInFs', '--max-count=2'] + ['--exclude-dir=' + d for d in ('proc', 'sys', 'dev', 'run', '.git', 'node_modules')] + ['--', query, root]
        try:
            run = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=SEARCH_SECONDS)
            output, timed_out = run.stdout, False
        except subprocess.TimeoutExpired as error:
            output, timed_out = (error.stdout or b'').decode(errors='replace') if isinstance(error.stdout, bytes) else (error.stdout or ''), True
        results = []
        for line in output.splitlines()[:MAX_RESULTS]:
            parts = line.split(':', 2)
            if len(parts) == 3 and parts[1].isdigit():
                results.append({'path': parts[0], 'line': int(parts[1]), 'text': parts[2][:200]})
        return {'mode': mode, 'root': root, 'query': query, 'results': results, 'command': command, 'timed_out': timed_out, 'limited': len(results) >= MAX_RESULTS}
    glob = any(ch in query for ch in '*?[')
    pattern = query if glob else '*' + query + '*'
    command = 'find %s -iname %s' % (q(root), q(pattern))
    lowered = pattern.lower()
    results, deadline, scanned, timed_out = [], time.monotonic() + SEARCH_SECONDS, 0, False
    stack = [root]
    while stack and len(results) < MAX_RESULTS:
        folder = stack.pop()
        if folder in SKIP_WALK:
            continue
        try:
            with os.scandir(folder) as it:
                for item in it:
                    scanned += 1
                    if time.monotonic() > deadline or scanned > 300000:
                        timed_out = True
                        stack.clear()
                        break
                    if fnmatch(item.name.lower(), lowered):
                        results.append({'path': item.path, 'type': 'dir' if item.is_dir(follow_symlinks=False) else 'file'})
                        if len(results) >= MAX_RESULTS:
                            break
                    if item.is_dir(follow_symlinks=False):
                        stack.append(item.path)
        except OSError:
            continue
    return {'mode': 'name', 'root': root, 'query': query, 'results': results, 'command': command, 'timed_out': timed_out, 'limited': len(results) >= MAX_RESULTS}


def places():
    out = []
    for raw, label, why in PLACES:
        path = os.path.expanduser(raw)
        if os.path.isdir(path):
            out.append({'path': path, 'label': label, 'why': why, 'command': 'cd %s' % q(path)})
    return out


ASSETS = {
    '/': ('text/html; charset=utf-8', (HERE / 'static' / 'index.html')),
    '/app.js': ('text/javascript; charset=utf-8', (HERE / 'static' / 'app.js')),
    '/style.css': ('text/css; charset=utf-8', (HERE / 'static' / 'style.css')),
}


class Handler(BaseHTTPRequestHandler):
    server_version = 'LinuxExplorer'
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def headers_ok(self):
        # Only this computer, only this app: blocks other websites from reading your files via your browser.
        host = (self.headers.get('Host') or '').lower()
        return host in ('localhost:%d' % self.server.server_address[1], '127.0.0.1:%d' % self.server.server_address[1])

    def send(self, status, body, ctype):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json(self, status, data):
        self.send(status, json.dumps(data).encode(), 'application/json')

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.headers_ok():
            return self.json(403, {'error': 'Not allowed.'})
        url = urlparse(self.path)
        if url.path in ASSETS:
            ctype, file = ASSETS[url.path]
            return self.send(200, file.read_bytes(), ctype)
        args = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == '/api/list':
                return self.json(200, list_dir(args.get('path', '~'), args.get('hidden') == '1'))
            if url.path == '/api/preview':
                return self.json(200, preview(args.get('path', '')))
            if url.path == '/api/search':
                return self.json(200, search(args.get('root', '~'), args.get('q', ''), args.get('mode', 'name')))
            if url.path == '/api/places':
                return self.json(200, {'places': places(), 'home': str(Path.home())})
            if url.path == '/api/health':
                return self.json(200, {'ok': True, 'app': 'linux-explorer'})
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError) as error:
            return self.json(404, {'error': str(error) or 'Not found.'})
        except PermissionError as error:
            return self.json(403, {'error': str(error)})
        except (ValueError, OSError) as error:
            return self.json(400, {'error': str(error)})
        return self.json(404, {'error': 'Not found.'})

    def do_POST(self):
        self.send_response(405)
        self.send_header('Allow', 'GET, HEAD')
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_PUT = do_DELETE = do_PATCH = do_POST


def make_server(port=PORT):
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def already_running(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1) as conn:
            conn.sendall(b'GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nConnection: close\r\n\r\n' % port)
            return b'linux-explorer' in conn.recv(4096)
    except OSError:
        return False


def main():
    url = 'http://localhost:%d/' % PORT
    if already_running(PORT):
        webbrowser.open(url)
        return
    server = make_server(PORT)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print('Linux Explorer is running at %s (close this window or press Ctrl+C to stop)' % url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
