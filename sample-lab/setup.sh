#!/usr/bin/env bash
# Creates a small, harmless practice area at sample-lab/lab for exploring with Linux Explorer.
# Everything in it is fake. Run it again any time to reset it.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB="$HERE/lab"
rm -rf "$LAB"
mkdir -p "$LAB"/{logs,notes,scripts,shared,tools,secrets,.ssh}

cat > "$LAB/logs/auth.log" <<'LOG'
Oct 27 08:01:10 server sshd[811]: Accepted password for alice from 192.0.2.10 port 51122 ssh2
Oct 27 08:03:22 server sshd[902]: Failed password for root from 203.0.113.9 port 40211 ssh2
Oct 27 08:03:25 server sshd[902]: Failed password for root from 203.0.113.9 port 40213 ssh2
Oct 27 08:03:28 server sshd[902]: Failed password for admin from 203.0.113.9 port 40215 ssh2
Oct 27 08:03:31 server sshd[902]: Failed password for oracle from 203.0.113.9 port 40217 ssh2
Oct 27 08:03:35 server sshd[902]: Failed password for root from 203.0.113.9 port 40219 ssh2
Oct 27 08:03:41 server sshd[902]: Accepted password for backup from 203.0.113.9 port 40223 ssh2
Oct 27 09:15:02 server sudo: alice : TTY=pts/0 ; COMMAND=/usr/bin/apt update
LOG
cat > "$LAB/logs/web.log" <<'LOG'
198.51.100.4 - - [27/Oct/2026:08:10:01] "GET /index.html HTTP/1.1" 200 5120
198.51.100.4 - - [27/Oct/2026:08:10:02] "GET /login.php HTTP/1.1" 200 2048
203.0.113.77 - - [27/Oct/2026:08:11:09] "GET /admin HTTP/1.1" 404 312
203.0.113.77 - - [27/Oct/2026:08:11:10] "GET /wp-login.php HTTP/1.1" 404 312
203.0.113.77 - - [27/Oct/2026:08:11:12] "GET /.env HTTP/1.1" 404 312
LOG
printf 'Things to check\n- who logged in at 08:03?\n- why is shared/ writable by everyone?\n' > "$LAB/notes/todo.txt"
printf '#!/usr/bin/env bash\necho "backing up..."\n' > "$LAB/scripts/backup.sh"; chmod 755 "$LAB/scripts/backup.sh"
printf 'anyone on this computer can edit me\n' > "$LAB/shared/notes.txt"; chmod 666 "$LAB/shared/notes.txt"
printf '#!/usr/bin/env bash\necho "pretend this runs with extra power"\n' > "$LAB/tools/suid-demo"; chmod 4755 "$LAB/tools/suid-demo"
printf 'username: demo\npassword: not-a-real-password\n' > "$LAB/secrets/passwords.txt"; chmod 644 "$LAB/secrets/passwords.txt"
printf 'ssh-ed25519 AAAA-fake-key demo@example\n' > "$LAB/.ssh/authorized_keys"; chmod 600 "$LAB/.ssh/authorized_keys"; chmod 700 "$LAB/.ssh"
echo "Practice area ready: $LAB"
echo "Open Linux Explorer, type that path in the bar, and press Go."
