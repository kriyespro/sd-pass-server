# Platform Goals — WordPress & CodeIgniter Support

## Current State (baseline)

- **Static sites only** — ZIP upload → extract to `data/sites/<project_id>/` → served by Django middleware
- **All Traefik routes → `http://web:8000`** — single Django upstream for every project type
- **`ProjectType`** has `WORDPRESS` and `PHP` as placeholders — nothing implemented
- **No Docker SDK** — no per-project container spawning
- **No MySQL** — postgres only (shared, platform DB); `provision_database_stub()` is unimplemented
- **`ProjectType.PHP`** exists → will be repurposed as `CODEIGNITER`

---

## Shared Infrastructure (required by both WordPress and CodeIgniter)

These pieces are prerequisites for both features.

### INF-1 — Add MySQL service to docker-compose

Add `mysql:8` service to `docker-compose.yml` and `docker-compose.prod.yml`.

```yaml
mysql:
  image: mysql:8
  restart: always
  environment:
    MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
  volumes:
    - mysqldata:/var/lib/mysql
  healthcheck:
    test: ['CMD', 'mysqladmin', 'ping', '-h', 'localhost']
    interval: 5s
    timeout: 5s
    retries: 10
```

Settings to add to `core/settings/base.py`:
```python
MYSQL_HOST = env('MYSQL_HOST', default='mysql')
MYSQL_PORT = env.int('MYSQL_PORT', default=3306)
MYSQL_ROOT_PASSWORD = env('MYSQL_ROOT_PASSWORD')
```

### INF-2 — Add docker-py to dependencies

```
docker>=7.0.0
```

Add to `requirements.txt`. Used for spawning/stopping per-project containers.

Settings:
```python
DOCKER_SOCKET = env('DOCKER_SOCKET', default='unix:///var/run/docker.sock')
```

Mount Docker socket in `web` and `worker` services:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

### INF-3 — Traefik upstream per project type

`apps/domains/services.py::write_project_router_file()` currently hardcodes `settings.TRAEFIK_UPSTREAM_URL` for all projects.

Change to resolve upstream dynamically:

```python
from apps.projects.models import ProjectType

def _upstream_for_project(project) -> str:
    if project.project_type in (ProjectType.WORDPRESS, ProjectType.PHP):
        return f'http://proj_{project.pk}:80'   # per-project container
    return settings.TRAEFIK_UPSTREAM_URL        # Django app
```

Pass `upstream_url=_upstream_for_project(project)` into the Jinja template context.

### INF-4 — Container lifecycle service

New file: `apps/containers/services.py`

Shared Docker helpers used by both WordPress and CodeIgniter provisioners:

```python
def get_docker_client()           # cached docker.from_env()
def container_name(project) -> str   # "proj_{project.pk}"
def get_container(project)           # returns Container or None
def stop_container(project)          # stop + remove
def container_is_running(project) -> bool
```

### INF-5 — MySQL provisioner service

New file: `apps/containers/mysql.py`

```python
def create_mysql_db(project) -> dict:
    """Create DB + dedicated user. Returns {db, user, password}."""

def drop_mysql_db(project) -> None:
    """Drop DB + user on project delete."""
```

Credentials stored encrypted in a new `ProjectDatabase` model:

```python
class ProjectDatabase(models.Model):
    project    = OneToOneField(Project, ...)
    db_name    = CharField(max_length=64)
    db_user    = CharField(max_length=64)
    db_password_enc = CharField(max_length=512)  # Fernet-encrypted
    created_at = DateTimeField(auto_now_add=True)
```

### INF-6 — Daily container health task

Add to `CELERY_BEAT_SCHEDULE` (runs every 10 min):

```python
'containers-health-check': {
    'task': 'containers.restart_crashed_containers',
    'schedule': crontab(minute='*/10'),
},
```

Task finds projects where `project_type in (WORDPRESS, PHP)` and `status = running` but container is not alive → restart container.

---

## Feature 1 — WordPress Support

### Overview

`wordpress:apache` Docker container per site. MySQL DB per site. User gets a working WP install on project creation — no ZIP upload needed.

### Model changes

Add `WordPressInstance` model in `apps/wordpress/models.py`:

```python
class WordPressInstance(models.Model):
    project        = OneToOneField(Project, on_delete=CASCADE)
    container_id   = CharField(max_length=64, blank=True)
    wp_admin_user  = CharField(max_length=64, default='admin')
    wp_admin_pass_enc = CharField(max_length=512)  # Fernet-encrypted
    wp_admin_email = CharField(max_length=254)
    created_at     = DateTimeField(auto_now_add=True)
    updated_at     = DateTimeField(auto_now=True)
```

### Provisioning flow (on project create)

Celery task: `wordpress.provision_wordpress_site`

```
1. create_mysql_db(project)         → {db, user, password}
2. docker run wordpress:apache
     --name proj_{project.pk}
     --restart always
     --network {platform_network}
     -e WORDPRESS_DB_HOST=mysql:3306
     -e WORDPRESS_DB_NAME={db}
     -e WORDPRESS_DB_USER={user}
     -e WORDPRESS_DB_PASSWORD={password}
     -e WORDPRESS_TABLE_PREFIX=wp_
     -e WORDPRESS_CONFIG_EXTRA=...
     -v data/sites/{project.pk}/:/var/www/html/
3. write_project_router_file(project)  → Traefik → http://proj_{project.pk}:80
4. wp_instance.container_id = container.id; save()
5. project.status = RUNNING; save()
6. Notification: "WordPress site is live at {url} | Admin: {url}/wp-admin"
```

### De-provisioning flow (on project delete)

```
1. stop_container(project)
2. drop_mysql_db(project)
3. shutil.rmtree(data/sites/{project.pk}/)
4. remove_project_router_file(project)
5. project.is_deleted = True; save()
```

### Suspension / unsuspension

- **Suspend** (trial ends / billing) → `docker stop proj_{project.pk}` (data preserved)
- **Unsuspend** (plan redeemed) → `docker start proj_{project.pk}`

### UI changes

| View | Change |
|---|---|
| `ProjectCreateView` | Hide ZIP upload, show WP admin email field for `wordpress` type |
| Project detail page | Show WP admin URL, DB name, reset admin password button |
| `ProjectDeleteView` | Trigger de-provision Celery task instead of direct file delete |

### New files

```
apps/wordpress/
  __init__.py
  apps.py
  models.py          WordPressInstance
  services.py        provision(), deprovision(), reset_admin_password()
  tasks.py           provision_wordpress_site, deprovision_wordpress_site
  admin.py
  migrations/
```

### Beat schedule entry

```python
'wordpress-health-check': {
    'task': 'containers.restart_crashed_containers',
    'schedule': crontab(minute='*/10'),
},
```

(Shared with CodeIgniter via INF-6.)

---

## Feature 2 — CodeIgniter Support

### Overview

CodeIgniter 4 is a PHP framework. User uploads a ZIP of their CI4 app. Platform extracts it, starts a `php:8.3-apache` container with the project files mounted, sets document root to `/var/www/html/public/` (CI4 standard). Optional MySQL provisioned on request.

### ProjectType change

Repurpose existing `PHP = 'php', 'PHP'` → rename display label to `'CodeIgniter'`:

```python
PHP = 'php', 'CodeIgniter (PHP)'
```

No migration needed — slug stays `php`, display label changes only.

### Provisioning flow (on ZIP upload + scan pass)

Celery task: `codeigniter.provision_codeigniter_site` (called after `deploy_after_scan`)

```
1. extract_zip(upload) → data/sites/{project.pk}/
2. (Optional) create_mysql_db(project) if .env contains DB_* vars
3. Write data/sites/{project.pk}/.env (CI4 env file):
     CI_ENVIRONMENT = production
     app.baseURL = https://{fqdn}/
     database.default.hostname = mysql
     database.default.database = {db}
     database.default.username = {user}
     database.default.password = {password}
4. docker run php:8.3-apache
     --name proj_{project.pk}
     --restart always
     --network {platform_network}
     -e APACHE_DOCUMENT_ROOT=/var/www/html/public
     -v data/sites/{project.pk}/:/var/www/html/
5. write_project_router_file(project)  → Traefik → http://proj_{project.pk}:80
6. project.status = RUNNING; save()
7. Notification: "CodeIgniter app is live at {url}"
```

### Re-deploy flow (subsequent uploads)

```
1. stop_container(project)
2. extract_zip(new_upload) → data/sites/{project.pk}/   (overwrite)
3. docker start proj_{project.pk}
4. Invalidate Traefik cache
```

### Document root configuration

Apache needs `APACHE_DOCUMENT_ROOT` set to `/var/www/html/public`.

Use a custom `apache2.conf` or entrypoint that sets `DocumentRoot` via env var. Official `php:8.x-apache` image supports this via:

```dockerfile
# Custom entrypoint snippet in a startup script injected at runtime:
sed -i "s|DocumentRoot /var/www/html|DocumentRoot ${APACHE_DOCUMENT_ROOT}|g" \
    /etc/apache2/sites-available/000-default.conf
```

Alternative: Use a minimal custom image `FROM php:8.3-apache` with the sed already baked in (push to platform's private registry).

### PHP extensions needed for CI4

- `pdo_mysql` (database)
- `intl` (internationalisation)
- `mbstring` (string handling)
- `json` (built-in since PHP 8)
- `xml` (built-in)

Installed via `docker-php-ext-install` in the custom image.

### De-provisioning flow

Same as WordPress:

```
1. stop_container(project)
2. drop_mysql_db(project)  (if provisioned)
3. shutil.rmtree(data/sites/{project.pk}/)
4. remove_project_router_file(project)
```

### UI changes

| View | Change |
|---|---|
| `ProjectCreateView` | Show ZIP upload (same as static) for `php` type |
| Project detail page | Show PHP version, document root, DB credentials panel (if DB provisioned) |
| Upload view | Accept ZIP, trigger CI provision task on scan pass |

### New files

```
apps/codeigniter/
  __init__.py
  apps.py
  services.py        provision(), deprovision(), redeploy()
  tasks.py           provision_ci_site, deprovision_ci_site
  admin.py
```

---

## Implementation Order

```
Phase 1 — Shared infrastructure
  INF-1  Add MySQL service to docker-compose
  INF-2  Add docker-py dependency + socket mount
  INF-3  Dynamic Traefik upstream per project type
  INF-4  Container lifecycle service (apps/containers/)
  INF-5  MySQL provisioner + ProjectDatabase model
  INF-6  Container health check Celery task

Phase 2 — WordPress
  WP-1   WordPressInstance model + migration
  WP-2   provision() / deprovision() services
  WP-3   Celery tasks (provision, deprovision)
  WP-4   ProjectCreateView changes + WP admin email field
  WP-5   Project detail panel (admin URL, DB name)
  WP-6   Suspend / unsuspend hooks in billing task

Phase 3 — CodeIgniter
  CI-1   Rename PHP label to 'CodeIgniter (PHP)'
  CI-2   provision() / deprovision() / redeploy() services
  CI-3   Celery task hooked into deploy_after_scan pipeline
  CI-4   .env writer for CI4 config
  CI-5   Custom php:8.3-apache image with correct document root + extensions
  CI-6   Project detail panel (PHP version, DB credentials)

Phase 4 — Billing gates
  BIL-1  Gate WordPress behind wordpress_pro plan (or allow on all paid plans)
  BIL-2  Suspend = docker stop, unsuspend = docker start for container-based projects
  BIL-3  Resource quota tracking (CPU/RAM per container via docker stats)
```

---

## Risk & Decisions Log

| # | Decision | Why |
|---|---|---|
| 1 | One container per project (not shared PHP-FPM) | Isolation; simpler routing; failed sites don't affect others |
| 2 | `wordpress:apache` (not FPM) | Apache bundled; no separate Nginx config per site |
| 3 | `php:8.3-apache` for CI4 (not FPM) | Same reasoning; simpler entrypoint |
| 4 | MySQL per-site DB, shared MySQL container | Cost; simpler than per-site MySQL containers |
| 5 | Files on host volume, not inside container layer | Survives container restart; re-deploy = file overwrite + restart |
| 6 | Traefik file-provider (already in use) | No API changes; just change `upstream_url` per project |
| 7 | `docker restart always` | Auto-recover on crash/reboot without orchestrator |
| 8 | WP: no ZIP upload; CI: ZIP upload required | WordPress installs itself; CodeIgniter needs app code |
