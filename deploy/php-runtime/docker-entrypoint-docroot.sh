#!/bin/sh
# Rewrites Apache's document root to $APACHE_DOCUMENT_ROOT before starting.
# Covers CodeIgniter/Laravel/Symfony's public/ convention and Drupal's web/
# convention without baking a framework assumption into the image itself.
# Default (unset) keeps stock /var/www/html for generic PHP with no public/ dir.
#
# Only sites-available/000-default.conf needs rewriting — stock apache2.conf's
# <Directory /var/www/> block already grants access to any subpath under it
# (/var/www/html, /var/www/html/public, /var/www/html/web, ...), so it's untouched.
set -e

DOCROOT="${APACHE_DOCUMENT_ROOT:-/var/www/html}"

sed -ri -e "s!/var/www/html!${DOCROOT}!g" /etc/apache2/sites-available/*.conf

exec "$@"
