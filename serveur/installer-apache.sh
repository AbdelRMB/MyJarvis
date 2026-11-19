#!/bin/bash
# À lancer UNE fois sur le VPS avec sudo : certificat HTTPS + site Apache pour jarvis.abdelrahimriche.com
# Prérequis : enregistrement DNS « jarvis » (A -> serveur) créé chez Cloudflare.
set -euo pipefail
DOM=jarvis.abdelrahimriche.com
cd "$(dirname "$0")"
certbot certonly --apache -d "$DOM" --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring
cp apache-jarvis.conf "/etc/apache2/sites-available/$DOM.conf"
a2enmod -q proxy proxy_http headers ssl rewrite >/dev/null
a2ensite -q "$DOM" >/dev/null
apache2ctl configtest
systemctl reload apache2
echo "OK : site Apache actif pour https://$DOM"
