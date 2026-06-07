from django.db import models


class AffiliateApplication(models.Model):
    class Platform(models.TextChoices):
        YOUTUBE = 'youtube', 'YouTube'
        INSTAGRAM = 'instagram', 'Instagram'
        TWITTER = 'twitter', 'Twitter / X'
        LINKEDIN = 'linkedin', 'LinkedIn'
        BLOG = 'blog', 'Blog / Website'
        TIKTOK = 'tiktok', 'TikTok'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    website = models.URLField(blank=True, help_text='Your main website or channel URL.')
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.OTHER)
    audience_size = models.CharField(
        max_length=30,
        blank=True,
        help_text='Approximate followers/subscribers (e.g. 5000, 10k).',
    )
    message = models.TextField(
        max_length=1000,
        help_text='Why do you want to become an affiliate? How will you promote Krizn?',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    admin_notes = models.TextField(blank=True, help_text='Internal notes (not shown to applicant).')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Affiliate Application'
        verbose_name_plural = 'Affiliate Applications'

    def __str__(self):
        return f'{self.name} <{self.email}> [{self.status}]'
