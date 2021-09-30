from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    CongressMaster,
    Congress,
    Event,
    Session,
    EventEntry,
    EventEntryPlayer,
    CongressNewsItem,
    CongressDownload,
    BasketItem,
    Category,
    PlayerBatchId,
    EventLog,
    EventPlayerDiscount,
    Bulletin,
    PartnershipDesk,
)

admin.site.register(CongressMaster)
admin.site.register(CongressDownload)
admin.site.register(Bulletin)
admin.site.register(Congress)
admin.site.register(PlayerBatchId)
admin.site.register(Category)


class EventModelAdmin(admin.ModelAdmin):
    list_display = (
        "event_name",
        "congress",
        "description",
    )
    search_fields = ("event_name", "congress__name", "description")
    readonly_fields = ("show_url",)

    def show_url(self, instance):
        url = reverse("events:admin_event_summary", kwargs={"event_id": instance.pk})
        return format_html(f"<a href='{url}'>{url}")

    show_url.short_description = "Event Admin URL"


admin.site.register(Event, EventModelAdmin)
admin.site.register(Session)
admin.site.register(EventEntry)
admin.site.register(EventEntryPlayer)
admin.site.register(CongressNewsItem)
admin.site.register(BasketItem)
admin.site.register(EventLog)
admin.site.register(PartnershipDesk)
admin.site.register(EventPlayerDiscount)
