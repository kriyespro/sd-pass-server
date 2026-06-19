from django.http import Http404
from django.views.generic import TemplateView

from .pages import PAGES, _FEATURES, _STEPS, _PLANS


class SeoLandingView(TemplateView):
    """Generic programmatic SEO landing page view."""

    def get_template_names(self):
        key = self._page_key()
        page = PAGES.get(key, {})
        if page.get('is_hub'):
            return ['pages/seo/hub.jinja']
        return ['pages/seo/landing.jinja']

    def _page_key(self):
        section = self.kwargs.get('section', '')
        slug = self.kwargs.get('slug', '')
        return f'{section}/{slug}' if slug else section

    def get(self, request, *args, **kwargs):
        if not PAGES.get(self._page_key()):
            raise Http404
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        key = self._page_key()
        page = PAGES[key]
        ctx.update({
            'page': page,
            'features': _FEATURES,
            'steps': _STEPS,
            'plans': _PLANS,
            'section': self.kwargs.get('section', ''),
            'slug': self.kwargs.get('slug', ''),
        })
        return ctx
