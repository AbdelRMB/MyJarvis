#!/bin/bash
# À lancer avec sudo sur le VPS après un changement de apache-jarvis.conf (le certificat existe déjà).
set -euo pipefail
DOM=jarvis.abdelrahimriche.com
cd "$(dirname "$0")"
cp "/etc/apache2/sites-available/$DOM.conf" "/etc/apache2/sites-available/$DOM.conf.avant-$(date +%Y%m%d-%H%M)"
cp apache-jarvis.conf "/etc/apache2/sites-available/$DOM.conf"
a2enmod -q proxy proxy_http headers ssl rewrite >/dev/null
if apache2ctl configtest; then
  systemctl reload apache2
  echo "OK : https://$DOM/mobile/"
else
  echo "Configuration refusée : l'ancienne est remise." >&2
  cp "$(ls -t /etc/apache2/sites-available/$DOM.conf.avant-* | head -1)" "/etc/apache2/sites-available/$DOM.conf"
  exit 1
fi
