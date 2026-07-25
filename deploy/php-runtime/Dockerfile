# Shared runtime image for generic PHP, CodeIgniter/Laravel-style PHP, and Drupal
# app containers (WordPress uses the official wordpress:apache image instead — it
# installs itself). See php.txt section 5.1.
#
# Build + push to the platform's private registry, then reference the tag from
# apps/containers/services.py when starting a project's app container.
FROM php:8.3-apache

# libzip-dev/unzip: Composer package extraction (create-project, install).
# libfreetype6-dev/libjpeg62-turbo-dev/libpng-dev: build deps for the gd extension.
# git: Composer VCS-sourced packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libzip-dev unzip git \
        libfreetype6-dev libjpeg62-turbo-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/* \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install pdo_mysql mysqli intl mbstring opcache gd zip \
    && a2enmod rewrite

# drush (Drupal CLI) available globally for apps/drupal's first-boot install step
# (php.txt section 6) — baked in here so no per-project download slows first boot.
RUN php -r "copy('https://getcomposer.org/installer', 'composer-setup.php');" \
    && php composer-setup.php --install-dir=/usr/local/bin --filename=composer \
    && rm composer-setup.php \
    && composer global require drush/drush --no-interaction \
    && ln -s /root/.composer/vendor/bin/drush /usr/local/bin/drush

COPY docker-entrypoint-docroot.sh /usr/local/bin/docker-entrypoint-docroot.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-docroot.sh

ENTRYPOINT ["docker-entrypoint-docroot.sh"]
CMD ["apache2-foreground"]
