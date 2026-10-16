from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Notification


@login_required
def notification_inbox(request):
    notifications = (
        request.user.notifications.all()[:50]
    )
    unread_count = request.user.notifications.filter(email_sent=False).count()
    return render(
        request,
        "notifications/inbox.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )
