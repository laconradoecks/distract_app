# DistractApp landing page

Static, single-file landing page ("Take a break from reality"), served by nginx on a DigitalOcean droplet.

```
public/                 # everything nginx serves
  index.html            # the landing page (fonts/images bundled inside)
  pinterest-86414.html  # Pinterest verification file (backup method)
deploy/
  nginx/distractapp.conf  # nginx server block
  deploy.sh               # pulls the latest commit onto the droplet
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

**Test URL (before DNS):** http://distractapp.138.197.117.174.sslip.io

The bare IP can't be used for this site: yosaki's nginx config already claims `138.197.117.174` as a server name.
sslip.io is public wildcard DNS that resolves that hostname to the droplet IP, so nginx can route it here.

## DNS (when the domain is ready)

At your domain registrar (or DigitalOcean → Networking → Domains), point the domain at the droplet:

| Type | Name  | Value           |
|------|-------|-----------------|
| A    | `@`   | 138.197.117.174 |
| A    | `www` | 138.197.117.174 |

Then, on the droplet, add the domain to the site and get HTTPS:

```bash
sed -i 's/server_name distractapp.138.197.117.174.sslip.io;/server_name yourdomain.com www.yourdomain.com distractapp.138.197.117.174.sslip.io;/' /etc/nginx/sites-available/distractapp
nginx -t && systemctl reload nginx
certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Finally, click **Verify** in Pinterest.

## Updating

```bash
git push
DROPLET=root@138.197.117.174 ./deploy/deploy.sh   # needs SSH key access, or run `git -C /var/www/distractapp pull` in the DO web console
```
