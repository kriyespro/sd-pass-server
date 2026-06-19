"""
Programmatic SEO page definitions.
Each entry: slug → page context dict used by SeoLandingView.
"""
from __future__ import annotations

# ── Shared feature bullets ────────────────────────────────────────────────────

_FEATURES = [
    {'icon': '🤖', 'title': 'AI Image Optimizer', 'body': 'Auto-compress images after every upload — faster pages, zero manual work.'},
    {'icon': '🔒', 'title': 'Free SSL (HTTPS)', 'body': "Every site gets automatic HTTPS via Let's Encrypt. No setup needed."},
    {'icon': '🌐', 'title': 'Instant Subdomain', 'body': 'Go live on yourname.apps.krizn.com in under 2 minutes.'},
    {'icon': '🔗', 'title': 'Custom Domain', 'body': 'Connect your own domain with guided DNS steps — free on paid plans.'},
    {'icon': '🔍', 'title': 'Security Scan', 'body': 'Every upload is scanned before publishing — keeps your site and visitors safe.'},
    {'icon': '📊', 'title': 'Live Server Dashboard', 'body': 'Monitor CPU, RAM, and disk from your dashboard — always know your site is healthy.'},
]

_STEPS = [
    {'n': '1', 'title': 'Sign up free', 'body': 'Create your account and get a 2-day free trial. No card required.', 'color': 'emerald'},
    {'n': '2', 'title': 'Upload your project', 'body': 'Drag a ZIP or folder. Krizn scans, optimizes with AI, and deploys automatically.', 'color': 'sky'},
    {'n': '3', 'title': 'Share your live URL', 'body': 'Get a subdomain instantly. Add your own domain anytime with one DNS record.', 'color': 'violet'},
]

_PLANS = [
    {'name': 'Free Trial', 'price': '₹0', 'period': '2 days', 'color': 'emerald', 'bullets': ['1 website', 'Subdomain included', 'AI optimizer', 'No card required']},
    {'name': 'Starter Trial', 'price': '₹299', 'period': '30 days', 'color': 'sky', 'bullets': ['1 website', 'Custom domain', 'SSL included', 'AI optimizer']},
    {'name': 'Launch Lite', 'price': '₹1,499', 'period': 'per year', 'color': 'violet', 'bullets': ['1 website', 'Custom domain', '1-year validity', 'Priority support']},
]

# ── Per-page data ─────────────────────────────────────────────────────────────

# Structure:
# 'section/slug' → {title, h1, meta_description, intro, badge, faq, og_title, og_description}

PAGES: dict[str, dict] = {

    # ── /hosting/ (hub) ───────────────────────────────────────────────────────
    'hosting': {
        'is_hub': True,
        'title': 'Cloud Hosting India — Affordable, Fast & Secure | Krizn',
        'h1': 'Cloud Hosting in India',
        'tagline': 'Affordable · Fast · Secure',
        'meta_description': 'Best cloud hosting in India for students and creators. Free 2-day trial, free SSL, custom domain. Plans from ₹299. Deploy in under 2 minutes.',
        'intro': 'Krizn is India\'s easiest cloud hosting platform. Deploy static websites and Python Flask apps to live URLs in under 2 minutes — no DevOps, no server setup.',
        'badge': '🇮🇳 India-based cloud hosting',
        'og_title': 'Cloud Hosting India — From ₹299 | Krizn',
        'og_description': 'Fast, secure cloud hosting in India. Free trial. Plans from ₹299. AI optimizer + free SSL included.',
        'children': [
            {'slug': 'for-students', 'label': 'For Students', 'icon': '🎓'},
            {'slug': 'python', 'label': 'Python Hosting', 'icon': '🐍'},
            {'slug': 'flask', 'label': 'Flask Hosting', 'icon': '⚗️'},
            {'slug': 'static-website', 'label': 'Static Sites', 'icon': '📄'},
            {'slug': 'portfolio', 'label': 'Portfolio', 'icon': '🎨'},
            {'slug': 'affordable', 'label': 'Affordable Plans', 'icon': '💰'},
            {'slug': 'with-ssl', 'label': 'Free SSL', 'icon': '🔒'},
            {'slug': 'custom-domain', 'label': 'Custom Domain', 'icon': '🔗'},
            {'slug': 'free-trial', 'label': 'Free Trial', 'icon': '🎁'},
        ],
    },

    # ── /hosting/<slug>/ landing pages ───────────────────────────────────────
    'hosting/for-students': {
        'title': 'Free Cloud Hosting for Students in India — Krizn',
        'h1': 'Free Cloud Hosting for Students in India',
        'tagline': 'Deploy your college project in 2 minutes',
        'meta_description': 'Host your student project website free. Get a live URL instantly. No credit card. Free SSL and subdomain. India-based cloud. Plans from ₹299.',
        'intro': 'Krizn is built for CS and IT students in India. Upload your project ZIP, get a live URL in under 2 minutes, and share it with your professor or recruiter today.',
        'badge': '🎓 Perfect for college projects',
        'og_title': 'Free Cloud Hosting for Students — Krizn India',
        'og_description': 'Deploy your student project free. Live URL in 2 minutes. No card required.',
        'faq': [
            ('Is Krizn free for students?', 'Yes — every account gets a 2-day free trial. You can host your project and share the live URL completely free. Paid plans start at ₹299.'),
            ('Do I need DevOps knowledge to use Krizn?', 'No. Just upload a ZIP of your HTML/CSS/JS project. Krizn handles everything else automatically.'),
            ('Can I use my own domain?', 'Yes. Custom domain support is included on all paid plans. You get a free subdomain on the free trial.'),
        ],
    },

    'hosting/python': {
        'title': 'Python Cloud Hosting India — Host Flask & Django Apps Free | Krizn',
        'h1': 'Python Cloud Hosting in India',
        'tagline': 'Deploy Flask and Python apps to the cloud',
        'meta_description': 'Host Python web apps in India. Flask app hosting with free trial. Custom domain, free SSL, AI optimizer. Plans from ₹299. Deploy in minutes.',
        'intro': 'Deploy your Python Flask application to a live cloud URL in minutes. Upload a ZIP of your Flask project — Krizn installs dependencies, starts Gunicorn, and gives you a live URL.',
        'badge': '🐍 Python & Flask app hosting',
        'og_title': 'Python Cloud Hosting India — Flask & Django | Krizn',
        'og_description': 'Host Python Flask apps in India. Free trial. Live URL in minutes. Plans from ₹299.',
        'faq': [
            ('Which Python frameworks does Krizn support?', 'Krizn supports Flask apps on paid plans. Upload a ZIP of your Flask project with a requirements.txt and app.py — we handle the rest.'),
            ('Does Krizn install my Python dependencies?', 'Yes. Krizn reads your requirements.txt and installs all dependencies automatically before starting your app.'),
            ('What Python version does Krizn use?', 'Python 3.11 is used in the Flask runner container.'),
        ],
    },

    'hosting/flask': {
        'title': 'Flask App Hosting India — Deploy Free | Krizn',
        'h1': 'Flask App Hosting in India',
        'tagline': 'From zip upload to live URL in minutes',
        'meta_description': 'Deploy Flask applications to Indian cloud servers. Free trial. Automatic pip install, Gunicorn, SSL. Plans from ₹299. No DevOps needed.',
        'intro': 'Krizn makes Flask deployment effortless. Upload your project ZIP, and Krizn automatically installs your requirements, starts a Gunicorn server, and gives you a secure live URL.',
        'badge': '⚗️ Flask deployment made simple',
        'og_title': 'Flask Hosting India — Deploy Your App Free | Krizn',
        'og_description': 'Host Flask apps in India. Auto pip install + Gunicorn. Free trial. Plans from ₹299.',
        'faq': [
            ('How do I deploy my Flask app on Krizn?', 'ZIP your Flask project folder (include app.py and requirements.txt), upload it on Krizn, and your app goes live automatically within minutes.'),
            ('Does Krizn support Flask with SQLite?', 'Yes. SQLite databases are supported inside Flask projects. For production use, consider upgrading to a plan with PostgreSQL support.'),
            ('What is the entry point for Flask on Krizn?', 'Krizn auto-detects app.py, main.py, wsgi.py, or run.py. Your Flask instance should be named app, application, or server.'),
        ],
    },

    'hosting/static-website': {
        'title': 'Free Static Website Hosting India — HTML CSS JS | Krizn',
        'h1': 'Free Static Website Hosting in India',
        'tagline': 'HTML, CSS, JS — live in 2 minutes',
        'meta_description': 'Host HTML, CSS, and JavaScript websites free in India. Instant subdomain, free SSL, AI image optimizer. No server needed. Plans from ₹299.',
        'intro': 'Krizn is the fastest way to host a static website in India. Upload your HTML folder or ZIP — get a secure live URL with AI-optimized images in under 2 minutes.',
        'badge': '📄 Static site hosting made easy',
        'og_title': 'Free Static Website Hosting India | Krizn',
        'og_description': 'Host HTML/CSS/JS sites free in India. Free SSL, AI optimizer, instant subdomain.',
        'faq': [
            ('What file types can I upload?', 'HTML, CSS, JS, images (PNG, JPG, WebP, SVG), fonts, and JSON files are all supported.'),
            ('Can I upload a multi-page website?', 'Yes. Upload a ZIP of your full folder structure. Krizn preserves all paths and serves your site correctly.'),
            ('Is there a file size limit?', 'Individual images should be under 300 KB. Total ZIP size up to 200 MB is supported.'),
        ],
    },

    'hosting/portfolio': {
        'title': 'Portfolio Website Hosting India — Free for Students & Developers | Krizn',
        'h1': 'Portfolio Website Hosting for Students & Developers',
        'tagline': 'Show your work. Get hired.',
        'meta_description': 'Host your portfolio website free in India. Live URL in 2 minutes. Free subdomain, custom domain support. AI image optimizer. Plans from ₹299.',
        'intro': 'Land your dream job with a live portfolio. Krizn gives students and developers a fast, secure place to host their portfolio — with a free subdomain and optional custom domain.',
        'badge': '🎨 Portfolio hosting for developers',
        'og_title': 'Free Portfolio Hosting India — Students & Developers | Krizn',
        'og_description': 'Host your portfolio free. Live URL in 2 minutes. Free subdomain + custom domain. India cloud.',
        'faq': [
            ('Can I connect my own domain to my portfolio?', 'Yes. Add your custom domain on any paid plan. Krizn guides you through DNS setup and issues an SSL certificate automatically.'),
            ('Will my portfolio be fast?', 'Yes. Krizn runs AI image compression after every upload and serves from India-based cloud infrastructure.'),
            ('Can I update my portfolio files?', 'Yes. Re-upload a new ZIP anytime to redeploy. Your URL stays the same.'),
        ],
    },

    'hosting/affordable': {
        'title': 'Cheap Cloud Hosting India — From ₹299 | Krizn',
        'h1': 'Affordable Cloud Hosting in India',
        'tagline': 'From ₹0 free trial to ₹1,499/year',
        'meta_description': 'Cheapest cloud hosting in India. Free 2-day trial, then ₹299 for 30 days or ₹1,499/year. Free SSL, custom domain, AI optimizer included.',
        'intro': 'Krizn offers the most affordable cloud hosting plans in India. Start free — no credit card. Then choose a plan that fits your budget, from ₹299 for 30 days to ₹1,499 for a full year.',
        'badge': '💰 India\'s most affordable cloud hosting',
        'og_title': 'Cheap Cloud Hosting India — From ₹299 | Krizn',
        'og_description': 'Most affordable cloud hosting in India. Free trial + plans from ₹299. SSL, AI optimizer included.',
        'faq': [
            ('What is the cheapest Krizn plan?', 'The Starter Trial is ₹299 for 30 days. You get 1 website, custom domain support, free SSL, and the AI image optimizer.'),
            ('Is there a yearly plan?', 'Yes. Launch Lite is ₹1,499 per year — the most cost-effective option for long-term hosting.'),
            ('Are there hidden fees?', 'No. All prices include SSL, subdomain, and the AI optimizer. You only pay for the plan you choose.'),
        ],
    },

    'hosting/with-ssl': {
        'title': 'Cloud Hosting with Free SSL Certificate India | Krizn',
        'h1': 'Cloud Hosting with Free SSL in India',
        'tagline': 'HTTPS on every site, automatically',
        'meta_description': 'All Krizn hosting plans include free SSL (HTTPS) via Let\'s Encrypt. Your site is always secure. India-based cloud. Plans from ₹299.',
        'intro': 'Every site hosted on Krizn is automatically secured with a free SSL certificate (HTTPS) via Let\'s Encrypt. No setup, no annual renewal fees — SSL is just included.',
        'badge': '🔒 Free SSL on every plan',
        'og_title': 'Cloud Hosting with Free SSL India | Krizn',
        'og_description': 'Free HTTPS SSL on every Krizn hosting plan. Auto-renewed. No setup needed. India cloud.',
        'faq': [
            ('Do I need to buy an SSL certificate separately?', 'No. Krizn automatically provisions and renews SSL certificates for free using Let\'s Encrypt.'),
            ('Does my custom domain also get free SSL?', 'Yes. When you connect a custom domain, Krizn issues a free SSL certificate for it automatically.'),
            ('What SSL type does Krizn use?', 'Krizn uses Let\'s Encrypt TLS certificates, which are trusted by all major browsers.'),
        ],
    },

    'hosting/custom-domain': {
        'title': 'Web Hosting with Custom Domain India — Free DNS + SSL | Krizn',
        'h1': 'Web Hosting with Custom Domain in India',
        'tagline': 'Connect your domain in minutes',
        'meta_description': 'Connect your own domain to Krizn hosting. Free SSL auto-setup, DNS verification guide. India-based cloud. Plans from ₹299.',
        'intro': 'Point your own domain to your Krizn site in minutes. Add an A record in your DNS, verify it on Krizn, and your site is live on your custom domain with free HTTPS.',
        'badge': '🔗 Custom domain on all paid plans',
        'og_title': 'Web Hosting with Custom Domain India | Krizn',
        'og_description': 'Connect your domain to Krizn. Free SSL, guided DNS setup. India cloud. Plans from ₹299.',
        'faq': [
            ('How do I connect my domain to Krizn?', 'Go to your project settings, enter your domain, then add an A record pointing to Krizn\'s server IP in your DNS provider. Krizn verifies and issues SSL automatically.'),
            ('Which DNS providers are supported?', 'Any DNS provider works — GoDaddy, Namecheap, Cloudflare, BigRock, etc. Just set the A record.'),
            ('How long does DNS propagation take?', 'Usually 5–30 minutes. Krizn checks automatically and notifies you when it\'s live.'),
        ],
    },

    'hosting/free-trial': {
        'title': 'Cloud Hosting Free Trial India — No Card Required | Krizn',
        'h1': 'Cloud Hosting Free Trial — No Credit Card',
        'tagline': '2 days free. Full platform access.',
        'meta_description': 'Try Krizn cloud hosting free for 2 days. No credit card required. Full platform access — AI optimizer, SSL, subdomain included. Upgrade from ₹299.',
        'intro': 'Start hosting your website completely free. Every new account gets 2 days of full platform access — no credit card, no hidden fees. Deploy your first site in under 2 minutes.',
        'badge': '🎁 2-day free trial — no card needed',
        'og_title': 'Free Cloud Hosting Trial India — No Card | Krizn',
        'og_description': '2-day free trial. Full platform. No credit card. India cloud hosting from ₹299 after trial.',
        'faq': [
            ('How long is the free trial?', '2 days from the moment you sign up. You get full access to all starter features including the AI optimizer, subdomain, and custom domain.'),
            ('Do I need a credit card for the free trial?', 'No. You can sign up with Google and start hosting immediately — no payment information required.'),
            ('What happens after the trial ends?', 'You can upgrade to the Starter Trial (₹299/30 days) or a yearly plan to keep your site live.'),
        ],
    },

    # ── /server/ (hub) ────────────────────────────────────────────────────────
    'server': {
        'is_hub': True,
        'title': 'Cloud Server Hosting India — Fast & Reliable | Krizn',
        'h1': 'Cloud Server Hosting in India',
        'tagline': 'Fast · Reliable · Affordable',
        'meta_description': 'Deploy to India-based cloud servers. Free 2-day trial, free SSL, AI optimizer. Host static sites and Flask apps. Plans from ₹299.',
        'intro': 'Krizn runs on India-based cloud infrastructure. Get a managed server environment for your websites and Python apps — without managing a server yourself.',
        'badge': '🇮🇳 India-based cloud servers',
        'og_title': 'Cloud Server Hosting India | Krizn',
        'og_description': 'India cloud servers for websites and Flask apps. Free trial. Plans from ₹299.',
        'children': [
            {'slug': 'for-students', 'label': 'For Students', 'icon': '🎓'},
            {'slug': 'deploy-website', 'label': 'Deploy Website', 'icon': '🚀'},
            {'slug': 'python', 'label': 'Python Server', 'icon': '🐍'},
            {'slug': 'affordable', 'label': 'Affordable', 'icon': '💰'},
            {'slug': 'with-ssl', 'label': 'Free SSL', 'icon': '🔒'},
        ],
    },

    # ── /server/<slug>/ landing pages ─────────────────────────────────────────
    'server/for-students': {
        'title': 'Free Cloud Server for Students India | Krizn',
        'h1': 'Free Cloud Server for Students in India',
        'tagline': 'Your project. On a real server. Free.',
        'meta_description': 'Get a free cloud server environment for your student project. Live URL in 2 minutes. No DevOps. India-based servers. Plans from ₹299.',
        'intro': 'Stop emailing ZIP files. Deploy your student project to a real cloud server in India and share a live URL with your professor or placement officer today.',
        'badge': '🎓 Cloud server for CS/IT students',
        'og_title': 'Free Cloud Server for Students India | Krizn',
        'og_description': 'Deploy student projects to India cloud servers. Free trial. Live URL in 2 minutes.',
        'faq': [
            ('Do I need to know Linux or DevOps?', 'No. Krizn abstracts away all server management. Just upload your project.'),
            ('Can I host my college project on Krizn?', 'Yes. Static HTML/CSS/JS projects and Flask Python apps are fully supported.'),
            ('Is it really free?', 'Yes, the 2-day free trial is completely free with no credit card.'),
        ],
    },

    'server/deploy-website': {
        'title': 'Deploy Website to Cloud Server India in Minutes | Krizn',
        'h1': 'Deploy Your Website to a Cloud Server in India',
        'tagline': 'Upload. Deploy. Share. Done.',
        'meta_description': 'Deploy your website to India cloud servers in under 2 minutes. Upload ZIP or folder — Krizn scans, optimizes, and publishes. Plans from ₹299.',
        'intro': 'Deploying to a cloud server used to mean SSH, Nginx configs, and SSL setup. With Krizn, you just upload a file and it\'s live.',
        'badge': '🚀 Deploy in under 2 minutes',
        'og_title': 'Deploy Website to India Cloud Server | Krizn',
        'og_description': 'Upload your site, get a live URL in 2 minutes. India cloud server. Plans from ₹299.',
        'faq': [
            ('How do I deploy my website on Krizn?', 'Sign up free, create a project, and upload your HTML folder or ZIP. Your site is live within 2 minutes.'),
            ('Can I update my site after deployment?', 'Yes. Re-upload a new ZIP anytime. Krizn redeploys automatically and your URL stays the same.'),
            ('What happens to my old files when I redeploy?', 'The previous version is replaced. Your project URL stays the same. Old files are removed.'),
        ],
    },

    'server/python': {
        'title': 'Python Server Hosting India — Flask & Web Apps | Krizn',
        'h1': 'Python Server Hosting in India',
        'tagline': 'Cloud server for Python web applications',
        'meta_description': 'Host Python Flask apps on India cloud servers. Automatic pip install, Gunicorn, SSL. Free trial. Plans from ₹299. No server config needed.',
        'intro': 'Run your Python web application on a managed cloud server in India. Upload your Flask project and Krizn automatically installs dependencies, configures Gunicorn, and serves it securely.',
        'badge': '🐍 Managed Python server India',
        'og_title': 'Python Server Hosting India | Krizn',
        'og_description': 'Managed Python/Flask server in India. Auto pip install + Gunicorn + SSL. Plans from ₹299.',
        'faq': [
            ('What Python version is used?', 'Python 3.11 in a managed container environment.'),
            ('Do I need to configure Gunicorn myself?', 'No. Krizn auto-detects your entry point and starts Gunicorn with sensible defaults.'),
            ('Can I use environment variables in my Flask app?', 'Yes. Set encrypted environment variables directly from your project dashboard.'),
        ],
    },

    'server/affordable': {
        'title': 'Affordable Cloud Server India — From ₹299 | Krizn',
        'h1': 'Affordable Cloud Server in India',
        'tagline': 'Professional server hosting at student prices',
        'meta_description': 'Cheapest cloud server hosting in India. Free trial, then from ₹299/month or ₹1,499/year. SSL, AI optimizer, custom domain included.',
        'intro': 'Krizn offers managed cloud server hosting at prices that work for students and early-stage startups. Start free — no credit card — and scale when you\'re ready.',
        'badge': '💰 Cheapest cloud server India',
        'og_title': 'Affordable Cloud Server India — From ₹299 | Krizn',
        'og_description': 'India\'s most affordable cloud server. Free trial. Plans from ₹299. SSL + AI optimizer included.',
        'faq': [
            ('What is the cheapest server plan?', 'Starter Trial at ₹299 for 30 days — includes 1 site, SSL, custom domain, and AI optimizer.'),
            ('Is there a yearly server plan?', 'Yes. Launch Lite at ₹1,499/year is our most popular option for long-term use.'),
            ('Are there bandwidth or traffic limits?', 'No metered bandwidth limits on standard plans. Fair use policy applies.'),
        ],
    },

    'server/with-ssl': {
        'title': 'Cloud Server with Free SSL India | Krizn',
        'h1': 'Cloud Server with Free SSL in India',
        'tagline': 'HTTPS everywhere — automatically',
        'meta_description': 'India cloud server with free automatic SSL (HTTPS) on every plan. Let\'s Encrypt, auto-renewed. No extra cost. Plans from ₹299.',
        'intro': 'Every Krizn server environment includes automatic HTTPS. No buying SSL certificates, no renewal reminders — it just works.',
        'badge': '🔒 Free SSL on every server plan',
        'og_title': 'Cloud Server with Free SSL India | Krizn',
        'og_description': 'Free HTTPS SSL on every Krizn server plan. Auto-renewed. No setup. India cloud.',
        'faq': [
            ('Does Krizn include SSL with the server plan?', 'Yes. All plans — including the free trial — include automatic HTTPS via Let\'s Encrypt.'),
            ('Do I need to renew the SSL certificate?', 'No. Krizn renews SSL automatically before expiry.'),
            ('Does my custom domain get SSL too?', 'Yes. When you connect a custom domain, a new SSL certificate is issued for it automatically.'),
        ],
    },
}
