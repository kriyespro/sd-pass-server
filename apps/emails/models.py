from django.db import models
from django.utils import timezone


class EmailTemplate(models.Model):
    TYPE_PAYMENT_RECEIPT = 'payment_receipt'
    TYPE_GETTING_STARTED = 'getting_started'
    TYPE_UPSELL_OFFER = 'upsell_offer'
    TYPE_ORDER = 'order'
    TYPE_RENEWAL = 'renewal'
    TYPE_AFFILIATE_TRAINING = 'affiliate_training'
    TYPE_ABANDONED_CART = 'abandoned_cart'
    TYPE_LEARNING_ACADEMY = 'learning_academy'
    TYPE_PARTNER = 'partner'
    TYPE_UPSELL = 'upsell'
    TYPE_REVIEW_COLLECTION = 'review_collection'

    TYPE_CHOICES = [
        (TYPE_PAYMENT_RECEIPT, 'Payment Receipt'),
        (TYPE_GETTING_STARTED, 'Getting Started Guide'),
        (TYPE_UPSELL_OFFER, 'Upsell Offer'),
        (TYPE_ORDER, 'Order Email'),
        (TYPE_RENEWAL, 'Renewal Email'),
        (TYPE_AFFILIATE_TRAINING, 'Affiliate Training'),
        (TYPE_ABANDONED_CART, 'Abandoned Cart'),
        (TYPE_LEARNING_ACADEMY, 'Learning Academy'),
        (TYPE_PARTNER, 'Partner Email'),
        (TYPE_UPSELL, 'Upsell Email'),
        (TYPE_REVIEW_COLLECTION, 'Review Collection'),
    ]

    template_type = models.CharField(
        max_length=30, choices=TYPE_CHOICES, unique=True, db_index=True
    )
    subject = models.CharField(max_length=255)
    html_body = models.TextField(
        help_text='Use {{placeholder}} syntax. See docs for available placeholders.'
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['template_type']
        verbose_name = 'Email Template'
        verbose_name_plural = 'Email Templates'

    def __str__(self):
        return self.get_template_type_display()


class EmailCampaign(models.Model):
    FREQ_WEEKLY    = 'weekly'
    FREQ_BIWEEKLY  = 'biweekly'
    FREQ_MONTHLY   = 'monthly'
    FREQ_CHOICES   = [
        (FREQ_WEEKLY,   'Weekly'),
        (FREQ_BIWEEKLY, 'Every 2 Weeks'),
        (FREQ_MONTHLY,  'Monthly'),
    ]

    name       = models.CharField(max_length=255)
    template   = models.ForeignKey('EmailTemplate', on_delete=models.CASCADE, related_name='campaigns')
    email_list = models.ForeignKey('EmailList',    on_delete=models.CASCADE, related_name='campaigns')
    frequency  = models.CharField(max_length=20, choices=FREQ_CHOICES)
    next_run_at = models.DateTimeField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['next_run_at']
        verbose_name = 'Email Campaign'
        verbose_name_plural = 'Email Campaigns'

    def __str__(self):
        return self.name

    @property
    def is_due(self):
        return self.is_active and self.next_run_at <= timezone.now()


class SMTPConfig(models.Model):
    host = models.CharField(max_length=255, default='us2.smtp.mailhostbox.com')
    port = models.IntegerField(default=587)
    username = models.EmailField(max_length=255, default='admin@krizn.com')
    password = models.CharField(max_length=255)
    use_tls = models.BooleanField(default=True)
    from_email = models.EmailField(max_length=255, default='admin@krizn.com')
    from_name = models.CharField(max_length=255, default='Krizn')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'SMTP Config'
        verbose_name_plural = 'SMTP Configs'

    def __str__(self):
        return f'{self.from_name} <{self.from_email}> via {self.host}:{self.port}'


class EmailList(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=500, blank=True)
    emails = models.TextField(help_text='One email address per line', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Email List'
        verbose_name_plural = 'Email Lists'

    def __str__(self):
        return self.name

    def get_emails(self):
        return [e.strip() for e in self.emails.splitlines() if e.strip()]

    @property
    def count(self):
        return len(self.get_emails())


class ScheduledEmail(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    ]

    template = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE, related_name='scheduled_emails')
    email_list = models.ForeignKey(
        EmailList, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_emails'
    )
    to_emails = models.TextField(blank=True, help_text='One email per line (used if no list selected)')
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_msg = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']
        verbose_name = 'Scheduled Email'
        verbose_name_plural = 'Scheduled Emails'

    def __str__(self):
        return f'{self.template} → {self.scheduled_at:%Y-%m-%d %H:%M}'

    def get_recipients(self):
        if self.email_list:
            return self.email_list.get_emails()
        return [e.strip() for e in self.to_emails.splitlines() if e.strip()]

    @property
    def is_due(self):
        return self.status == self.STATUS_PENDING and self.scheduled_at <= timezone.now()
