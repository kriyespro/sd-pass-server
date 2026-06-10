from django.shortcuts import render


def home(request):
    response = render(request, 'pages/home.jinja', {})
    if not request.user.is_authenticated:
        response['Cache-Control'] = 'public, max-age=300, stale-while-revalidate=60'
    return response


def handler404(request, exception):
    return render(request, 'pages/errors/404.jinja', status=404)


def handler500(request):
    return render(request, 'pages/errors/500.jinja', status=500)
