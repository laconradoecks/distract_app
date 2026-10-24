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

The droplet already runs another project, so this adds a second nginx site next to it.

```bash
ssh root@DROPLET_IP
sudo git clone https://github.com/laconradoecks/distract_app.git /var/www/distractapp
sudo cp /var/www/distractapp/deploy/nginx/distractapp.conf /etc/nginx/sites-available/distractapp
sudo sed -i 's/DOMAIN_HERE/yourdomain.com/g' /etc/nginx/sites-available/distractapp
sudo ln -s /etc/nginx/sites-available/distractapp /etc/nginx/sites-enabled/distractapp
sudo nginx -t && sudo systemctl reload nginx
```

## DNS

At your domain registrar (or DigitalOcean → Networking → Domains), point the domain at the droplet:

| Type | Name  | Value       |
|------|-------|-------------|
| A    | `@`   | DROPLET_IP  |
| A    | `www` | DROPLET_IP  |

Then, once `http://yourdomain.com` loads the page, add HTTPS:

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Updating

```bash
git push
DROPLET=root@DROPLET_IP ./deploy/deploy.sh
```
