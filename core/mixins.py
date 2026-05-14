"""Reusable view mixins."""


class SafePaginationMixin:
    """
    Paginate with ``Paginator.get_page()`` so invalid ``?page=`` values
    (0, negative, non-numeric) never raise ``EmptyPage`` / ``Http404``.
    """

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page_kwarg = self.page_kwarg
        raw = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg)
        page_obj = paginator.get_page(raw)
        return paginator, page_obj, page_obj.object_list, page_obj.has_other_pages()
