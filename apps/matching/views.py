from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.accounts.models import Interest

@login_required
def matching_radar_view(request):
    """Renders the Random Chat radar search page with optional topic / mode."""
    mode = request.GET.get('mode', 'interests')
    interest_slug = request.GET.get('interest', '').strip()
    interest_obj = None
    if interest_slug:
        interest_obj = Interest.objects.filter(slug=interest_slug).first()

    return render(request, 'matching/queue.html', {
        'mode': mode,
        'interest_slug': interest_slug,
        'interest_obj': interest_obj,
        'all_interests': Interest.objects.all(),
    })
