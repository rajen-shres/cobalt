import os

from django.db import models
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation


def _results_file_directory_path(instance, filename):
    """We want to save results files in a club folder"""

    now = timezone.now()
    date_str = now.strftime("%Y-%m-%d")

    return f"results/club_{instance.organisation.id}/{date_str}/{filename}"


class ResultsFile(models.Model):
    """Initially this supports clubs uploading files in USEBIO format. This may need to be extended for other
    formats and we will also need to decide if we use files at all when/if we put scoring into Cobalt"""

    class ResultsStatus(models.TextChoices):
        PUBLISHED = "PU"
        PENDING = "PE"

    results_file = models.FileField(upload_to=_results_file_directory_path)
    description = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
    )
    status = models.CharField(
        max_length=2, choices=ResultsStatus.choices, default=ResultsStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.results_file.path}"

    def filename(self):
        return os.path.basename(self.results_file.name)


class PlayerSummaryResult(models.Model):
    """Short summary of a players results, for high level views"""

    player_system_number = models.PositiveIntegerField()
    """ system number of player who played in this event """
    result_date = models.DateField()
    """ date event took place """
    position = models.PositiveIntegerField(blank=True, null=True)
    """ optional - where the player finished """
    percentage = models.FloatField(blank=True, null=True)
    """ optional what percentage they got """
    result_string = models.CharField(max_length=200, null=True, blank=True)
    """ de-normalised string to show as summary """
    event_name = models.CharField(max_length=200, null=True, blank=True)
    """ name of event """
    results_file = models.ForeignKey(
        ResultsFile,
        on_delete=models.CASCADE,
    )
    """ linked results file - may need to make this optional later depending on
        whether we generate files when we do scoring ourselves  """

    def __str__(self):
        return f"{self.player_system_number} - {self.event_name}"
