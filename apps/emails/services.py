import html as _html
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import certifi
    _SSL_CAFILE = certifi.where()
except ImportError:
    _SSL_CAFILE = None

from django.utils import timezone

from .models import EmailList, EmailTemplate, ScheduledEmail, SMTPConfig

# Placeholders available per template type
TEMPLATE_PLACEHOLDERS = {
    EmailTemplate.TYPE_PAYMENT_RECEIPT: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{payment_amount}}', 'Amount paid e.g. $49.00'),
        ('{{payment_date}}', 'Date of payment'),
        ('{{payment_method}}', 'e.g. Credit Card, PayPal'),
        ('{{invoice_number}}', 'Invoice or transaction ID'),
        ('{{plan_name}}', 'Subscription plan name'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_GETTING_STARTED: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{dashboard_url}}', 'Link to user dashboard'),
        ('{{support_email}}', 'Support email address'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_UPSELL_OFFER: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{offer_name}}', 'Name of the upsell offer'),
        ('{{offer_price}}', 'Price of the offer'),
        ('{{offer_url}}', 'Link to the offer page'),
        ('{{discount_code}}', 'Promo/discount code'),
        ('{{discount_percent}}', 'Discount percentage'),
        ('{{expiry_date}}', 'Offer expiry date'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_ORDER: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{order_id}}', 'Order ID'),
        ('{{order_date}}', 'Order date'),
        ('{{order_items}}', 'List of items ordered'),
        ('{{order_total}}', 'Order total amount'),
        ('{{order_status}}', 'Current order status'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_RENEWAL: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{renewal_date}}', 'Next renewal date'),
        ('{{plan_name}}', 'Subscription plan name'),
        ('{{renewal_amount}}', 'Amount to be charged'),
        ('{{billing_url}}', 'Link to billing page'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_AFFILIATE_TRAINING: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{affiliate_link}}', 'Unique affiliate referral link'),
        ('{{commission_rate}}', 'Commission percentage'),
        ('{{training_url}}', 'Link to affiliate training resources'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_ABANDONED_CART: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{cart_items}}', 'Items left in cart'),
        ('{{cart_url}}', 'Link to recover cart'),
        ('{{cart_total}}', 'Cart total value'),
        ('{{discount_code}}', 'Optional recovery discount code'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_LEARNING_ACADEMY: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{course_name}}', 'Name of the course'),
        ('{{lesson_url}}', 'Link to next lesson'),
        ('{{progress_percent}}', 'Course completion percentage'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_PARTNER: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{partner_name}}', 'Partner company/person name'),
        ('{{partner_dashboard_url}}', 'Link to partner portal'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_UPSELL: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{offer_name}}', 'Name of the upsell product'),
        ('{{offer_price}}', 'Price of the upsell'),
        ('{{offer_url}}', 'Link to the upsell page'),
        ('{{current_plan}}', "User's current plan"),
        ('{{upgrade_url}}', 'Link to upgrade page'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
    EmailTemplate.TYPE_REVIEW_COLLECTION: [
        ('{{user_name}}', "Recipient's full name"),
        ('{{user_email}}', "Recipient's email address"),
        ('{{product_name}}', 'Product/service they purchased'),
        ('{{order_id}}', 'Order reference'),
        ('{{review_url}}', 'Link to leave a review'),
        ('{{site_name}}', 'Platform name'),
        ('{{site_url}}', 'Platform URL'),
    ],
}


def get_placeholders_for_type(template_type: str) -> list:
    return TEMPLATE_PLACEHOLDERS.get(template_type, [])


def render_template(html_body: str, context: dict) -> str:
    result = html_body
    for key, value in context.items():
        safe_value = _html.escape(str(value), quote=False)
        result = result.replace('{{' + key + '}}', safe_value)
    return result


def get_active_smtp_config() -> SMTPConfig | None:
    return SMTPConfig.objects.filter(is_active=True).first()


def send_email(to_email: str, subject: str, html_body: str, smtp_config: SMTPConfig) -> tuple[bool, str]:
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'{smtp_config.from_name} <{smtp_config.from_email}>'
        msg['To'] = to_email

        msg.attach(MIMEText(html_body, 'html'))

        context = ssl.create_default_context(cafile=_SSL_CAFILE)
        with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=15) as server:
            if smtp_config.use_tls:
                server.starttls(context=context)
            server.login(smtp_config.username, smtp_config.password)
            server.sendmail(smtp_config.from_email, to_email, msg.as_string())

        return True, 'Email sent successfully.'
    except smtplib.SMTPAuthenticationError:
        return False, 'SMTP authentication failed. Check username/password.'
    except smtplib.SMTPConnectError:
        return False, f'Cannot connect to {smtp_config.host}:{smtp_config.port}.'
    except Exception as exc:
        return False, str(exc)


_EMAIL_BASE = '''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">
  <tr><td style="background:#1e293b;padding:28px 32px;text-align:center">
    <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700">{{site_name}}</h1>
  </td></tr>
  <tr><td style="padding:32px">
    {CONTENT}
  </td></tr>
  <tr><td style="background:#f8fafc;padding:20px 32px;text-align:center;border-top:1px solid #e2e8f0">
    <p style="margin:0;color:#94a3b8;font-size:12px">© {{site_name}} · <a href="{{site_url}}" style="color:#6366f1;text-decoration:none">{{site_url}}</a></p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>'''


def _base(content: str) -> str:
    return _EMAIL_BASE.replace('{CONTENT}', content)


DEFAULT_HTML_BODIES: dict[str, str] = {
    EmailTemplate.TYPE_PAYMENT_RECEIPT: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Payment Receipt</h2>
<p style="margin:0 0 24px;color:#64748b;font-size:14px">Hi {{user_name}}, thank you for your payment.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;margin-bottom:24px">
  <tr style="background:#f8fafc"><td style="padding:12px 16px;color:#64748b;font-size:13px;font-weight:600">Invoice</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right">{{invoice_number}}</td></tr>
  <tr><td style="padding:12px 16px;color:#64748b;font-size:13px;border-top:1px solid #e2e8f0">Plan</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right;border-top:1px solid #e2e8f0">{{plan_name}}</td></tr>
  <tr style="background:#f8fafc"><td style="padding:12px 16px;color:#64748b;font-size:13px;border-top:1px solid #e2e8f0">Date</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right;border-top:1px solid #e2e8f0">{{payment_date}}</td></tr>
  <tr><td style="padding:12px 16px;color:#64748b;font-size:13px;border-top:1px solid #e2e8f0">Method</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right;border-top:1px solid #e2e8f0">{{payment_method}}</td></tr>
  <tr style="background:#1e293b"><td style="padding:14px 16px;color:#ffffff;font-size:14px;font-weight:700;border-top:1px solid #e2e8f0">Total Paid</td><td style="padding:14px 16px;color:#4ade80;font-size:16px;font-weight:700;text-align:right;border-top:1px solid #e2e8f0">{{payment_amount}}</td></tr>
</table>
<p style="margin:0 0 6px;color:#64748b;font-size:13px">Need help? Contact us at <a href="mailto:{{support_email}}" style="color:#6366f1">{{support_email}}</a></p>'''),

    EmailTemplate.TYPE_GETTING_STARTED: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Welcome to {{site_name}}! 🎉</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, your account is ready. Here's how to get started:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px">
  <tr><td style="padding:12px 0;border-bottom:1px solid #e2e8f0"><span style="display:inline-block;background:#6366f1;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:12px;font-weight:700;margin-right:12px">1</span><span style="color:#1e293b;font-size:14px">Log in to your dashboard and explore your account</span></td></tr>
  <tr><td style="padding:12px 0;border-bottom:1px solid #e2e8f0"><span style="display:inline-block;background:#6366f1;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:12px;font-weight:700;margin-right:12px">2</span><span style="color:#1e293b;font-size:14px">Set up your first project and customize your settings</span></td></tr>
  <tr><td style="padding:12px 0"><span style="display:inline-block;background:#6366f1;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:12px;font-weight:700;margin-right:12px">3</span><span style="color:#1e293b;font-size:14px">Reach out if you need help — we're always here</span></td></tr>
</table>
<a href="{{dashboard_url}}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600">Go to Dashboard →</a>
<p style="margin:24px 0 0;color:#94a3b8;font-size:12px">Questions? Email us at <a href="mailto:{{support_email}}" style="color:#6366f1">{{support_email}}</a></p>'''),

    EmailTemplate.TYPE_UPSELL_OFFER: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Exclusive Offer for You 🔥</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, we have a special deal just for you:</p>
<div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:8px;padding:24px;margin-bottom:24px;text-align:center">
  <p style="margin:0 0 4px;color:rgba(255,255,255,0.8);font-size:13px;text-transform:uppercase;letter-spacing:1px">Special Offer</p>
  <h3 style="margin:0 0 8px;color:#ffffff;font-size:22px;font-weight:700">{{offer_name}}</h3>
  <p style="margin:0 0 16px;color:rgba(255,255,255,0.9);font-size:28px;font-weight:700">{{offer_price}}</p>
  <p style="margin:0 0 16px;color:rgba(255,255,255,0.8);font-size:13px">Save {{discount_percent}} with code: <strong style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:4px">{{discount_code}}</strong></p>
  <a href="{{offer_url}}" style="display:inline-block;background:#ffffff;color:#6366f1;text-decoration:none;padding:12px 32px;border-radius:6px;font-size:14px;font-weight:700">Claim Offer →</a>
</div>
<p style="margin:0;color:#94a3b8;font-size:12px;text-align:center">Offer expires {{expiry_date}}</p>'''),

    EmailTemplate.TYPE_ORDER: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Order Confirmed ✅</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, your order has been received.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;margin-bottom:24px">
  <tr style="background:#f8fafc"><td style="padding:12px 16px;color:#64748b;font-size:13px;font-weight:600">Order ID</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right">{{order_id}}</td></tr>
  <tr><td style="padding:12px 16px;color:#64748b;font-size:13px;border-top:1px solid #e2e8f0">Date</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right;border-top:1px solid #e2e8f0">{{order_date}}</td></tr>
  <tr style="background:#f8fafc"><td style="padding:12px 16px;color:#64748b;font-size:13px;border-top:1px solid #e2e8f0">Items</td><td style="padding:12px 16px;color:#1e293b;font-size:13px;text-align:right;border-top:1px solid #e2e8f0">{{order_items}}</td></tr>
  <tr><td style="padding:12px 16px;color:#64748b;font-size:13px;border-top:1px solid #e2e8f0">Status</td><td style="padding:12px 16px;color:#16a34a;font-size:13px;font-weight:600;text-align:right;border-top:1px solid #e2e8f0">{{order_status}}</td></tr>
  <tr style="background:#1e293b"><td style="padding:14px 16px;color:#ffffff;font-size:14px;font-weight:700;border-top:1px solid #e2e8f0">Total</td><td style="padding:14px 16px;color:#4ade80;font-size:16px;font-weight:700;text-align:right;border-top:1px solid #e2e8f0">{{order_total}}</td></tr>
</table>'''),

    EmailTemplate.TYPE_RENEWAL: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Upcoming Renewal Reminder</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, your subscription renews soon.</p>
<div style="background:#fefce8;border:1px solid #fde047;border-radius:8px;padding:20px;margin-bottom:24px">
  <p style="margin:0 0 8px;color:#854d0e;font-size:14px;font-weight:600">📅 Renewal Date: {{renewal_date}}</p>
  <p style="margin:0 0 8px;color:#854d0e;font-size:14px">Plan: <strong>{{plan_name}}</strong></p>
  <p style="margin:0;color:#854d0e;font-size:16px;font-weight:700">Amount: {{renewal_amount}}</p>
</div>
<p style="margin:0 0 16px;color:#64748b;font-size:13px">Your subscription will auto-renew. To manage billing, visit your billing page.</p>
<a href="{{billing_url}}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600">Manage Billing →</a>'''),

    EmailTemplate.TYPE_AFFILIATE_TRAINING: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Your Affiliate Training is Ready 🚀</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, start earning with {{site_name}}.</p>
<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:20px;margin-bottom:24px">
  <p style="margin:0 0 6px;color:#166534;font-size:13px;font-weight:600">Your Affiliate Link:</p>
  <p style="margin:0 0 12px;background:#dcfce7;padding:10px;border-radius:4px;font-family:monospace;font-size:13px;color:#15803d;word-break:break-all">{{affiliate_link}}</p>
  <p style="margin:0;color:#166534;font-size:14px;font-weight:600">Commission Rate: {{commission_rate}}</p>
</div>
<p style="margin:0 0 16px;color:#64748b;font-size:13px">Complete your affiliate training to start driving referrals and earning commissions.</p>
<a href="{{training_url}}" style="display:inline-block;background:#16a34a;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600">Start Training →</a>'''),

    EmailTemplate.TYPE_ABANDONED_CART: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">You left something behind 🛒</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, your cart is waiting for you.</p>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:24px">
  <p style="margin:0 0 8px;color:#475569;font-size:14px">Items in your cart: <strong>{{cart_items}}</strong></p>
  <p style="margin:0;color:#1e293b;font-size:18px;font-weight:700">Total: {{cart_total}}</p>
</div>
{% if discount_code %}<div style="background:#fef3c7;border-radius:6px;padding:12px 16px;margin-bottom:20px;text-align:center"><p style="margin:0;color:#92400e;font-size:14px">Use code <strong style="background:#fff;padding:2px 8px;border-radius:4px">{{discount_code}}</strong> for a special discount!</p></div>{% endif %}
<a href="{{cart_url}}" style="display:inline-block;background:#ef4444;color:#ffffff;text-decoration:none;padding:14px 32px;border-radius:6px;font-size:15px;font-weight:700">Complete My Purchase →</a>'''),

    EmailTemplate.TYPE_LEARNING_ACADEMY: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Keep Learning! 📚</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, continue your progress in {{course_name}}.</p>
<div style="margin-bottom:20px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
    <span style="color:#475569;font-size:13px;font-weight:600">Your Progress</span>
    <span style="color:#6366f1;font-size:13px;font-weight:700">{{progress_percent}}</span>
  </div>
  <div style="background:#e2e8f0;border-radius:999px;height:8px;overflow:hidden">
    <div style="background:#6366f1;height:8px;border-radius:999px;width:{{progress_percent}}"></div>
  </div>
</div>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Pick up where you left off and complete your next lesson.</p>
<a href="{{lesson_url}}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600">Continue Learning →</a>'''),

    EmailTemplate.TYPE_PARTNER: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Partner Update from {{site_name}}</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, here's an update for {{partner_name}}.</p>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:24px">
  <p style="margin:0 0 8px;color:#475569;font-size:13px">Partner Account: <strong style="color:#1e293b">{{partner_name}}</strong></p>
  <p style="margin:0;color:#475569;font-size:13px">Access your partner dashboard for reports, commissions, and resources.</p>
</div>
<a href="{{partner_dashboard_url}}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600">Partner Dashboard →</a>'''),

    EmailTemplate.TYPE_UPSELL: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">Ready to level up? ⚡</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, you're on the <strong>{{current_plan}}</strong> plan. Here's what you unlock by upgrading:</p>
<div style="background:linear-gradient(135deg,#1e293b,#334155);border-radius:8px;padding:24px;margin-bottom:24px">
  <h3 style="margin:0 0 12px;color:#ffffff;font-size:18px">{{offer_name}}</h3>
  <p style="margin:0 0 16px;color:#94a3b8;font-size:13px">Get more power, more resources, and priority support.</p>
  <p style="margin:0 0 20px;color:#4ade80;font-size:24px;font-weight:700">{{offer_price}}</p>
  <a href="{{upgrade_url}}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600">Upgrade Now →</a>
</div>
<p style="margin:0;color:#94a3b8;font-size:12px">Or <a href="{{offer_url}}" style="color:#6366f1">view full offer details</a></p>'''),

    EmailTemplate.TYPE_REVIEW_COLLECTION: _base('''
<h2 style="margin:0 0 8px;color:#1e293b;font-size:20px">How was your experience? ⭐</h2>
<p style="margin:0 0 20px;color:#64748b;font-size:14px">Hi {{user_name}}, we hope you're loving {{product_name}}!</p>
<div style="text-align:center;margin-bottom:28px">
  <p style="margin:0 0 16px;color:#475569;font-size:28px;letter-spacing:4px">★★★★★</p>
  <p style="margin:0 0 20px;color:#64748b;font-size:14px">Your feedback helps us improve and helps others make informed decisions. It takes less than 60 seconds!</p>
  <a href="{{review_url}}" style="display:inline-block;background:#f59e0b;color:#ffffff;text-decoration:none;padding:14px 36px;border-radius:6px;font-size:15px;font-weight:700">Leave a Review →</a>
</div>
<p style="margin:0;color:#94a3b8;font-size:12px;text-align:center">Order reference: {{order_id}}</p>'''),
}


def get_default_html_body(template_type: str) -> str:
    return DEFAULT_HTML_BODIES.get(template_type, '')


def get_all_users_emails() -> list[str]:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return list(User.objects.filter(is_active=True).values_list('email', flat=True))


def populate_list_from_users(email_list: EmailList, filter_type: str = 'all') -> int:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if filter_type == 'staff':
        qs = qs.filter(is_staff=True)
    emails = list(qs.values_list('email', flat=True))
    existing = set(email_list.get_emails())
    new_emails = [e for e in emails if e not in existing]
    if new_emails:
        current = email_list.emails.strip()
        addition = '\n'.join(new_emails)
        email_list.emails = (current + '\n' + addition).strip() if current else addition
        email_list.save()
    return len(new_emails)


AUTO_LIST_SEGMENTS = [
    ('all_users',       'All Active Users',     'Every active registered user'),
    ('staff',           'Staff',                'Staff and superusers only'),
    ('free',            'Free Plan',            'Users on the free plan'),
    ('test_plan',       'Starter Trial',        'Starter Trial plan users'),
    ('launch_lite',     'Launch Lite',          'Launch Lite plan users'),
    ('starter_cloud',   'Starter Cloud',        'Starter Cloud plan users'),
    ('wordpress_pro',   'WordPress Pro',        'WordPress Pro plan users'),
    ('business_cloud',  'Business Cloud',       'Business Cloud plan users'),
    ('agency_turbo',    'Agency Turbo',         'Agency Turbo plan users'),
    ('performance_max', 'Performance Max',      'Performance Max plan users'),
    ('paid',            'All Paid Subscribers', 'All users on any paid plan'),
    ('no_subscription', 'No Subscription',      'Users with no subscription record'),
]


def _emails_for_segment(segment: str) -> list[str]:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = User.objects.filter(is_active=True)

    if segment == 'all_users':
        pass
    elif segment == 'staff':
        qs = qs.filter(is_staff=True)
    elif segment == 'no_subscription':
        qs = qs.filter(subscription__isnull=True)
    elif segment == 'paid':
        qs = qs.filter(
            subscription__isnull=False,
            subscription__status='active',
        ).exclude(subscription__plan_slug='free')
    else:
        qs = qs.filter(subscription__plan_slug=segment, subscription__status='active')

    return list(qs.values_list('email', flat=True))


def auto_create_list(segment: str) -> tuple[EmailList, int]:
    label = next((lbl for slug, lbl, _ in AUTO_LIST_SEGMENTS if slug == segment), segment)
    description = next((desc for slug, _, desc in AUTO_LIST_SEGMENTS if slug == segment), '')

    emails = _emails_for_segment(segment)
    email_list, _ = EmailList.objects.get_or_create(
        name=label,
        defaults={'description': description},
    )
    email_list.description = description
    email_list.emails = '\n'.join(emails)
    email_list.save()
    return email_list, len(emails)


def send_scheduled_email(scheduled: ScheduledEmail) -> tuple[bool, str, int]:
    smtp = get_active_smtp_config()
    if not smtp:
        scheduled.status = ScheduledEmail.STATUS_FAILED
        scheduled.error_msg = 'No active SMTP config.'
        scheduled.save()
        return False, 'No active SMTP config.', 0

    recipients = scheduled.get_recipients()
    if not recipients:
        scheduled.status = ScheduledEmail.STATUS_FAILED
        scheduled.error_msg = 'No recipients.'
        scheduled.save()
        return False, 'No recipients.', 0

    sample_ctx = {
        'user_name': 'Subscriber',
        'user_email': '',
        'site_name': smtp.from_name,
        'site_url': 'https://krizn.com',
        'support_email': smtp.from_email,
        'dashboard_url': 'https://krizn.com/dashboard',
        'plan_name': 'Your Plan',
        'payment_amount': '',
        'payment_date': '',
        'payment_method': '',
        'invoice_number': '',
        'offer_name': '',
        'offer_price': '',
        'offer_url': '',
        'discount_code': '',
        'discount_percent': '',
        'expiry_date': '',
        'order_id': '',
        'order_date': '',
        'order_items': '',
        'order_total': '',
        'order_status': '',
        'renewal_date': '',
        'renewal_amount': '',
        'billing_url': 'https://krizn.com/billing',
        'affiliate_link': '',
        'commission_rate': '',
        'training_url': '',
        'cart_items': '',
        'cart_url': '',
        'cart_total': '',
        'course_name': '',
        'lesson_url': '',
        'progress_percent': '',
        'partner_name': '',
        'partner_dashboard_url': '',
        'current_plan': '',
        'upgrade_url': '',
        'product_name': '',
        'review_url': '',
    }

    sent_count = 0
    errors = []
    for email in recipients:
        ctx = {**sample_ctx, 'user_email': email}
        html_body = render_template(scheduled.template.html_body, ctx)
        subject = render_template(scheduled.template.subject, ctx)
        ok, msg = send_email(email, subject, html_body, smtp)
        if ok:
            sent_count += 1
        else:
            errors.append(f'{email}: {msg}')

    if errors:
        scheduled.status = ScheduledEmail.STATUS_FAILED
        scheduled.error_msg = '\n'.join(errors)
    else:
        scheduled.status = ScheduledEmail.STATUS_SENT
    scheduled.sent_at = timezone.now()
    scheduled.save()
    return not bool(errors), f'Sent {sent_count}/{len(recipients)}', sent_count


def process_due_scheduled_emails() -> int:
    due = ScheduledEmail.objects.filter(
        status=ScheduledEmail.STATUS_PENDING,
        scheduled_at__lte=timezone.now(),
    )
    total = 0
    for item in due:
        _, _, count = send_scheduled_email(item)
        total += count
    return total


def _advance_campaign(campaign) -> None:
    from dateutil.relativedelta import relativedelta
    from .models import EmailCampaign
    base = campaign.next_run_at
    if campaign.frequency == EmailCampaign.FREQ_WEEKLY:
        campaign.next_run_at = base + relativedelta(weeks=1)
    elif campaign.frequency == EmailCampaign.FREQ_BIWEEKLY:
        campaign.next_run_at = base + relativedelta(weeks=2)
    elif campaign.frequency == EmailCampaign.FREQ_MONTHLY:
        campaign.next_run_at = base + relativedelta(months=1)
    campaign.last_run_at = timezone.now()
    campaign.save()


def run_campaign(campaign) -> tuple[bool, str, int]:
    smtp = get_active_smtp_config()
    if not smtp:
        return False, 'No active SMTP config.', 0

    recipients = campaign.email_list.get_emails()
    if not recipients:
        return False, 'Email list is empty.', 0

    base_ctx = {
        'user_name': 'Subscriber',
        'user_email': '',
        'site_name': smtp.from_name,
        'site_url': 'https://krizn.com',
        'support_email': smtp.from_email,
        'dashboard_url': 'https://krizn.com/dashboard',
        'plan_name': '', 'payment_amount': '', 'payment_date': '',
        'payment_method': '', 'invoice_number': '', 'offer_name': '',
        'offer_price': '', 'offer_url': '', 'discount_code': '',
        'discount_percent': '', 'expiry_date': '', 'order_id': '',
        'order_date': '', 'order_items': '', 'order_total': '',
        'order_status': '', 'renewal_date': '', 'renewal_amount': '',
        'billing_url': 'https://krizn.com/billing', 'affiliate_link': '',
        'commission_rate': '', 'training_url': '', 'cart_items': '',
        'cart_url': '', 'cart_total': '', 'course_name': '',
        'lesson_url': '', 'progress_percent': '', 'partner_name': '',
        'partner_dashboard_url': '', 'current_plan': '', 'upgrade_url': '',
        'product_name': '', 'review_url': '',
    }

    sent_count = 0
    errors = []
    for email in recipients:
        ctx = {**base_ctx, 'user_email': email}
        html_body = render_template(campaign.template.html_body, ctx)
        subject = render_template(campaign.template.subject, ctx)
        ok, msg = send_email(email, subject, html_body, smtp)
        if ok:
            sent_count += 1
        else:
            errors.append(f'{email}: {msg}')

    _advance_campaign(campaign)
    return not bool(errors), f'Sent {sent_count}/{len(recipients)}', sent_count


def process_due_campaigns() -> int:
    from .models import EmailCampaign
    due = EmailCampaign.objects.filter(is_active=True, next_run_at__lte=timezone.now())
    total = 0
    for c in due:
        _, _, count = run_campaign(c)
        total += count
    return total


def send_template_email(template_type: str, to_email: str, context: dict) -> tuple[bool, str]:
    try:
        template = EmailTemplate.objects.get(template_type=template_type, is_active=True)
    except EmailTemplate.DoesNotExist:
        return False, f'No active template found for type: {template_type}'

    smtp = get_active_smtp_config()
    if not smtp:
        return False, 'No active SMTP config found.'

    html_body = render_template(template.html_body, context)
    subject = render_template(template.subject, context)
    return send_email(to_email, subject, html_body, smtp)
