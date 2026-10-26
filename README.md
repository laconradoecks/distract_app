# DistractApp landing page

Static, single-file landing page ("Take a break from reality"), served by nginx on a DigitalOcean droplet.

```
public/                 # everything nginx serves
  index.html            # the landing page (fonts/images bundled inside)
  pinterest-86414.html  # Pinterest verification file (backup method)
deploy/
  nginx/distractapp.conf          # nginx server block (starting template)
  nginx/waitlist-locations.conf   # /api/waitlist + password-protected /admin/
  nginx/waitlist-ratelimit.conf   # 5 signups/min per IP
  waitlist/app.py                 # waitlist service (Python stdlib + SQLite)
  waitlist/distractapp-waitlist.service
  deploy.sh                       # pulls the latest commit onto the droplet
```

## Pinterest verification

`public/index.html` carries the Pinterest tag in its `<head>`:

```html
<meta name="p:domain_verify" content="86414f71319723a6c81cfac72f6fa3c9"/>
```

Once the domain serves this page, click **Verify** in Pinterest (Settings → Claimed accounts → Websites).
The file `pinterest-86414.html` is also served at `https://DOMAIN/pinterest-86414.html` in case you picked the
"upload HTML file" method instead.

## First-time setup on the droplet

Hosted on the **yosaki** droplet (`138.197.117.174`, NYC3) next to yosaki.com. Done on 2026-10-24:

```bash
git clone https://github.com/laconradoecks/distract_app.git /var/www/distractapp
cp /var/www/distractapp/deploy/nginx/distractapp.conf /etc/nginx/sites-available/distractapp
sed -i 's/server_name DOMAIN_HERE www.DOMAIN_HERE;/server_name distractapp.138.197.117.174.sslip.io;/' /etc/nginx/sites-available/distractapp
ln -s /etc/nginx/sites-available/distractapp /etc/nginx/sites-enabled/distractapp
nginx -t && systemctl reload nginx
```

**Test URL (HTTP only):** http://distractapp.138.197.117.174.sslip.io

The bare IP can't be used for this site: yosaki's nginx config already claims `138.197.117.174` as a server name.
sslip.io is public wildcard DNS that resolves that hostname to the droplet IP, so nginx can route it here.

## Live: https://distractapp.com

Went live 2026-10-24. DNS is at Namecheap (BasicDNS) with A records `@` and `www` → `138.197.117.174`.

On the droplet, the domain was added to the site and HTTPS issued:

```bash
sed -i 's/server_name distractapp.138.197.117.174.sslip.io;/server_name distractapp.com www.distractapp.com distractapp.138.197.117.174.sslip.io;/' /etc/nginx/sites-available/distractapp
nginx -t && systemctl reload nginx
certbot --nginx --non-interactive --redirect -d distractapp.com -d www.distractapp.com
```

Certbot now manages the live file `/etc/nginx/sites-available/distractapp` (HTTPS block + HTTP→HTTPS redirect) and renews
the certificate automatically. Edit that file on the server directly; `deploy/nginx/distractapp.conf` is only the starting template.
Backup of the pre-certbot config: `/root/distractapp.nginx.bak`.

## Waitlist

Both email forms POST to `/api/waitlist`, which nginx forwards to a small Python service on `127.0.0.1:8787`
(systemd unit `distractapp-waitlist`). Emails are stored in SQLite at `/var/lib/distractapp/waitlist.db`.
Duplicates are ignored, a hidden honeypot field drops bots, and nginx rate-limits each IP.

**Download the list:** open https://distractapp.com/admin/, sign in, click **Download CSV**.

Install (as root on the droplet):

```bash
cp /var/www/distractapp/deploy/waitlist/distractapp-waitlist.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now distractapp-waitlist
cp /var/www/distractapp/deploy/nginx/waitlist-ratelimit.conf /etc/nginx/conf.d/distractapp-waitlist-ratelimit.conf
cp /var/www/distractapp/deploy/nginx/waitlist-locations.conf /etc/nginx/snippets/distractapp-waitlist.conf
# add `include snippets/distractapp-waitlist.conf;` inside the 443 server block of /etc/nginx/sites-available/distractapp
nginx -t && systemctl reload nginx
```

Set or change the admin password (asks for it twice, never shown on screen; username `distractapp`):

```bash
printf 'distractapp:%s\n' "$(openssl passwd -apr1)" > /etc/nginx/distractapp-admin.htpasswd
```

After editing `app.py`: `git pull` on the droplet, then `systemctl restart distractapp-waitlist`.

Back up the list: `sqlite3 /var/lib/distractapp/waitlist.db .dump > waitlist-backup.sql` (or just download the CSV).

## Updating

```bash
git push
DROPLET=root@138.197.117.174 ./deploy/deploy.sh   # needs SSH key access, or run `git -C /var/www/distractapp pull` in the DO web console
```
