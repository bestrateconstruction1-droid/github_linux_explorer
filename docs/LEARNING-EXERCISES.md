# Learning exercises

Do these in the practice lab. Set it up once:

```bash
./sample-lab/setup.sh
```

Open Linux Explorer, paste the path it prints (it ends in `sample-lab/lab`) into the bar, and press **Go**. Try each exercise in the app first, then run the terminal command and compare. Every terminal command below was run against this lab and gives the answer shown.

In the terminal, first go to the lab:

```bash
cd sample-lab/lab
```

## 1. Who tried to log in, and failed?

**In the app:** open `logs/auth.log`. Then go back to the lab folder, search for **Text inside files**, and look for `Failed password`.

**In the terminal:**

```bash
grep 'Failed password' logs/auth.log | awk '{print $11}' | sort | uniq -c | sort -rn
```

**Answer:** `5  203.0.113.9`. One address failed five times in under a minute.

Which usernames did it try?

```bash
grep 'Failed password' logs/auth.log | awk '{print $9}' | sort | uniq -c | sort -rn
```

**Answer:** `root` (3 times), `admin`, `oracle`. These are classic guesses.

## 2. Did the attacker get in?

```bash
grep Accepted logs/auth.log | grep 203.0.113.9
```

**Answer:** yes. `Accepted password for backup from 203.0.113.9` appears a few seconds after the failures. A success right after many failures from the same address is the most worrying pattern in a log. A real analyst would escalate this.

## 3. Which files can anyone edit?

**In the app:** open the `shared` folder. The file has a **⚠ notable** badge. Click it and read the warning.

```bash
find . -type f -perm -002
```

**Answer:** `./shared/notes.txt`. The permissions show `-rw-rw-rw-`: the last `rw-` means everyone can change it.

## 4. Which programs run with extra power (SUID)?

**In the app:** open `tools` and click `suid-demo`. Look at the permissions: `-rwsr-xr-x`. The `s` is the SUID bit.

```bash
find . -type f -perm -4000
```

**Answer:** `./tools/suid-demo`. On a real system, attackers look for SUID programs owned by root.

## 5. What is hidden, and why do the permissions matter?

**In the app:** tick **Hidden files**. A folder called `.ssh` appears.

```bash
ls -la
ls -l .ssh
```

**Answer:** `.ssh` is `drwx------` and the key file inside is `-rw-------`. Only the owner can touch them. SSH refuses to use keys that other people can read, which is why these permissions are tight.

## 6. Who is probing the website?

**In the app:** open `logs/web.log` and look for the `404` lines.

```bash
grep ' 404 ' logs/web.log | awk '{print $1, $6}' | sort | uniq -c
```

**Answer:** one address, `203.0.113.77`, asked for `/admin`, `/wp-login.php` and `/.env`, which are pages that attackers look for. Nothing was found (404), but the pattern is reconnaissance.

## Challenge

Without any hints, find out:

1. What time was the first failed login?
2. Is there anything in `secrets/` that shouldn't be readable by everyone?
3. Write three sentences, as if for a ticket: what happened, what evidence you have, and what you would do next.

Writing it down is the real skill. Analysts are trusted for clear, short notes.
