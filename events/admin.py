from django.contrib import admin
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
admin.site.register(Event)
admin.site.register(Session)
admin.site.register(EventEntry)
admin.site.register(EventEntryPlayer)
admin.site.register(CongressNewsItem)
admin.site.register(BasketItem)
admin.site.register(EventLog)
admin.site.register(PartnershipDesk)
admin.site.register(EventPlayerDiscount)
