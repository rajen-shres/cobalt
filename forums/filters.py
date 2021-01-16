import django_filters

# from django import forms
from .models import Post


class PostFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr="icontains")
    # This is cool, but not useful here
    #    groups = django_filters.ModelMultipleChoiceFilter(queryset=Forum.objects.all(),
    #        widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Post
        fields = ["title", "author", "forum"]
