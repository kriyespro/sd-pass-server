from django.shortcuts import render


def home(request):
    return render(request, 'pages/home.jinja', {})


def handler404(request, exception):
    return render(request, 'pages/errors/404.jinja', status=404)


def handler500(request):
    return render(request, 'pages/errors/500.jinja', status=500)
