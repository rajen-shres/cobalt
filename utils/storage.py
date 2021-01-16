from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """ If we update static files such as .js or .css files then user's
        browsers will still cache the old version causing problems.
        We could disable caching but that would make the system much slower.
        Instead we use ManifestStaticFilesStorage which sticks an MD5 hash
        on the end of the filename making it unique.

        We need to do three things though to make it work properly. First
        we need to ignore errors if it can't find an entry in its
        staticfiles.json. We do this with manifest_strict = False
        See https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#django.contrib.staticfiles.storage.ManifestStaticFilesStorage.manifest_strict

        Secondly we sub-class it here so we can ignore missing file
        references.

        Thirdly, we need to use relative paths so {% static "/ddd" %}
        won't work. It needs to be {% static "ddd" %}
        """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            result = super().hashed_name(name, content, filename)
        except ValueError:
            # When the file is missing, let's forgive and ignore that.
            result = name
        return result
