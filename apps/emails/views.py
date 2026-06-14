from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, TemplateView, View

from .forms import EmailCampaignForm, EmailListForm, EmailTemplateForm, ScheduledEmailForm, SMTPConfigForm, TestEmailForm
from .models import EmailCampaign, EmailList, EmailTemplate, ScheduledEmail, SMTPConfig
from .services import (
    AUTO_LIST_SEGMENTS,
    auto_create_list,
    get_active_smtp_config,
    get_default_html_body,
    get_placeholders_for_type,
    populate_list_from_users,
    process_due_campaigns,
    render_template,
    run_campaign,
    send_email,
    send_scheduled_email,
)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


class EmailTemplateListView(StaffRequiredMixin, ListView):
    model = EmailTemplate
    template_name = 'pages/admin_monitor/emails/list.jinja'
    context_object_name = 'templates'

    def get_queryset(self):
        return EmailTemplate.objects.all().order_by('template_type')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        existing_types = set(self.get_queryset().values_list('template_type', flat=True))
        ctx['all_types'] = EmailTemplate.TYPE_CHOICES
        ctx['existing_types'] = existing_types
        ctx['smtp_config'] = get_active_smtp_config()
        return ctx


class EmailTemplateCreateView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/edit.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        template_type = self.kwargs.get('template_type')
        form = EmailTemplateForm(initial={'template_type': template_type})
        ctx['form'] = form
        ctx['template_obj'] = None
        ctx['placeholders'] = get_placeholders_for_type(template_type)
        ctx['template_type'] = template_type
        return ctx

    def post(self, request, template_type):
        form = EmailTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Email template created.')
            return redirect('admin_emails:list')
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        template_type = self.kwargs.get('template_type')
        ctx['form'] = form or EmailTemplateForm(initial={'template_type': template_type})
        ctx['template_obj'] = None
        ctx['placeholders'] = get_placeholders_for_type(template_type)
        ctx['template_type'] = template_type
        return ctx


class EmailTemplateEditView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/edit.jinja'

    def _get_obj(self):
        return get_object_or_404(EmailTemplate, pk=self.kwargs['pk'])

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self._get_obj()
        ctx['form'] = form or EmailTemplateForm(instance=obj)
        ctx['template_obj'] = obj
        ctx['placeholders'] = get_placeholders_for_type(obj.template_type)
        ctx['template_type'] = obj.template_type
        return ctx

    def post(self, request, pk):
        obj = self._get_obj()
        form = EmailTemplateForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Email template updated.')
            return redirect('admin_emails:list')
        return self.render_to_response(self.get_context_data(form=form))


class EmailTemplateDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(EmailTemplate, pk=pk)
        obj.delete()
        messages.success(request, f'Template "{obj}" deleted.')
        return redirect('admin_emails:list')


class EmailTemplateSendTestView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/send_test.jinja'

    def _get_obj(self):
        return get_object_or_404(EmailTemplate, pk=self.kwargs['pk'])

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['template_obj'] = self._get_obj()
        ctx['form'] = form or TestEmailForm()
        ctx['smtp_config'] = get_active_smtp_config()
        return ctx

    def post(self, request, pk):
        obj = self._get_obj()
        form = TestEmailForm(request.POST)
        if form.is_valid():
            smtp = get_active_smtp_config()
            if not smtp:
                messages.error(request, 'No active SMTP config. Set one up first.')
                return self.render_to_response(self.get_context_data(form=form))

            sample_ctx = {
                'user_name': 'Test User',
                'user_email': form.cleaned_data['to_email'],
                'payment_amount': '$49.00',
                'payment_date': '2026-06-12',
                'payment_method': 'Credit Card',
                'invoice_number': 'INV-0001',
                'plan_name': 'Pro Plan',
                'dashboard_url': 'https://krizn.com/dashboard',
                'support_email': 'admin@krizn.com',
                'offer_name': 'Premium Upgrade',
                'offer_price': '$99.00',
                'offer_url': 'https://krizn.com/offer',
                'discount_code': 'SAVE20',
                'discount_percent': '20%',
                'expiry_date': '2026-07-01',
                'order_id': 'ORD-12345',
                'order_date': '2026-06-12',
                'order_items': 'Pro Plan x1',
                'order_total': '$49.00',
                'order_status': 'Completed',
                'renewal_date': '2026-07-12',
                'renewal_amount': '$49.00',
                'billing_url': 'https://krizn.com/billing',
                'affiliate_link': 'https://krizn.com/ref/testuser',
                'commission_rate': '30%',
                'training_url': 'https://krizn.com/affiliate/training',
                'cart_items': 'Pro Plan',
                'cart_url': 'https://krizn.com/cart',
                'cart_total': '$49.00',
                'course_name': 'Django Mastery',
                'lesson_url': 'https://krizn.com/learn/lesson-1',
                'progress_percent': '45%',
                'partner_name': 'Partner Corp',
                'partner_dashboard_url': 'https://krizn.com/partner',
                'current_plan': 'Starter',
                'upgrade_url': 'https://krizn.com/upgrade',
                'product_name': 'Pro Plan',
                'review_url': 'https://krizn.com/review',
                'site_name': 'Krizn',
                'site_url': 'https://krizn.com',
            }

            html_body = render_template(obj.html_body, sample_ctx)
            subject = render_template(obj.subject, sample_ctx)
            ok, msg = send_email(form.cleaned_data['to_email'], subject, html_body, smtp)

            if ok:
                messages.success(request, f'Test email sent to {form.cleaned_data["to_email"]}.')
                return redirect('admin_emails:list')
            else:
                messages.error(request, f'Send failed: {msg}')

        return self.render_to_response(self.get_context_data(form=form))


class SMTPConfigView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/smtp.jinja'

    def _get_or_create(self):
        obj = SMTPConfig.objects.filter(is_active=True).first()
        if not obj:
            obj = SMTPConfig.objects.first()
        return obj

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self._get_or_create()
        ctx['form'] = form or SMTPConfigForm(instance=obj)
        ctx['smtp_config'] = obj
        return ctx

    def post(self, request):
        obj = self._get_or_create()
        form = SMTPConfigForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'SMTP config saved.')
            return redirect('admin_emails:smtp')
        return self.render_to_response(self.get_context_data(form=form))


class LoadDefaultTemplateView(StaffRequiredMixin, View):
    def get(self, request, template_type):
        html = get_default_html_body(template_type)
        return JsonResponse({'html': html})


# ── Email Lists ──────────────────────────────────────────────────────────────

class EmailListListView(StaffRequiredMixin, ListView):
    model = EmailList
    template_name = 'pages/admin_monitor/emails/email_lists.jinja'
    context_object_name = 'lists'

    def get_queryset(self):
        return EmailList.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['segments'] = AUTO_LIST_SEGMENTS
        return ctx


class EmailListEditView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/email_list_edit.jinja'

    def _get_obj(self):
        pk = self.kwargs.get('pk')
        return get_object_or_404(EmailList, pk=pk) if pk else None

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self._get_obj()
        ctx['form'] = form or EmailListForm(instance=obj)
        ctx['list_obj'] = obj
        return ctx

    def post(self, request, pk=None):
        obj = self._get_obj()
        form = EmailListForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Email list saved.')
            return redirect('admin_emails:email_lists')
        return self.render_to_response(self.get_context_data(form=form))


class EmailListDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(EmailList, pk=pk)
        obj.delete()
        messages.success(request, f'List "{obj.name}" deleted.')
        return redirect('admin_emails:email_lists')


class EmailListPopulateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(EmailList, pk=pk)
        filter_type = request.POST.get('filter', 'all')
        added = populate_list_from_users(obj, filter_type)
        messages.success(request, f'Added {added} email(s) from users.')
        return redirect('admin_emails:email_list_edit', pk=pk)


class AutoCreateListView(StaffRequiredMixin, View):
    def post(self, request, segment):
        email_list, count = auto_create_list(segment)
        messages.success(request, f'"{email_list.name}" synced — {count} recipient(s).')
        return redirect('admin_emails:email_lists')


# ── Scheduled Emails ─────────────────────────────────────────────────────────

class ScheduledEmailListView(StaffRequiredMixin, ListView):
    model = ScheduledEmail
    template_name = 'pages/admin_monitor/emails/scheduled.jinja'
    context_object_name = 'scheduled_emails'

    def get_queryset(self):
        return ScheduledEmail.objects.select_related('template', 'email_list').all()


class ScheduledEmailCreateView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/scheduled_edit.jinja'

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = form or ScheduledEmailForm()
        ctx['scheduled_obj'] = None
        return ctx

    def post(self, request):
        form = ScheduledEmailForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Scheduled email created.')
            return redirect('admin_emails:scheduled')
        return self.render_to_response(self.get_context_data(form=form))


class ScheduledEmailDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(ScheduledEmail, pk=pk)
        obj.delete()
        messages.success(request, 'Scheduled email deleted.')
        return redirect('admin_emails:scheduled')


class ScheduledEmailSendNowView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(ScheduledEmail, pk=pk)
        ok, msg, count = send_scheduled_email(obj)
        if ok:
            messages.success(request, f'Sent to {count} recipient(s). {msg}')
        else:
            messages.error(request, f'Send failed: {msg}')
        return redirect('admin_emails:scheduled')


# ── Campaigns ────────────────────────────────────────────────────────────────

class CampaignListView(StaffRequiredMixin, ListView):
    model = EmailCampaign
    template_name = 'pages/admin_monitor/emails/campaigns.jinja'
    context_object_name = 'campaigns'

    def get_queryset(self):
        return EmailCampaign.objects.select_related('template', 'email_list').all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['due_count'] = EmailCampaign.objects.filter(
            is_active=True, next_run_at__lte=timezone.now()
        ).count()
        return ctx


class CampaignEditView(StaffRequiredMixin, TemplateView):
    template_name = 'pages/admin_monitor/emails/campaign_edit.jinja'

    def _get_obj(self):
        pk = self.kwargs.get('pk')
        return get_object_or_404(EmailCampaign, pk=pk) if pk else None

    def get_context_data(self, form=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self._get_obj()
        ctx['form'] = form or EmailCampaignForm(instance=obj)
        ctx['campaign'] = obj
        ctx['templates'] = EmailTemplate.objects.filter(is_active=True)
        ctx['email_lists'] = EmailList.objects.all()
        ctx['freq_choices'] = EmailCampaign.FREQ_CHOICES
        return ctx

    def post(self, request, pk=None):
        obj = self._get_obj()
        form = EmailCampaignForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Campaign saved.')
            return redirect('admin_emails:campaigns')
        return self.render_to_response(self.get_context_data(form=form))


class CampaignDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(EmailCampaign, pk=pk)
        obj.delete()
        messages.success(request, f'Campaign "{obj.name}" deleted.')
        return redirect('admin_emails:campaigns')


class CampaignToggleView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(EmailCampaign, pk=pk)
        obj.is_active = not obj.is_active
        obj.save()
        state = 'activated' if obj.is_active else 'paused'
        messages.success(request, f'Campaign "{obj.name}" {state}.')
        return redirect('admin_emails:campaigns')


class CampaignRunNowView(StaffRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(EmailCampaign, pk=pk)
        ok, msg, count = run_campaign(obj)
        if ok:
            messages.success(request, f'"{obj.name}" sent to {count} recipient(s). Next run: {obj.next_run_at:%Y-%m-%d %H:%M}')
        else:
            messages.error(request, f'Send failed: {msg}')
        return redirect('admin_emails:campaigns')


class ProcessDueCampaignsView(StaffRequiredMixin, View):
    def post(self, request):
        total = process_due_campaigns()
        messages.success(request, f'Processed due campaigns. {total} email(s) sent.')
        return redirect('admin_emails:campaigns')
