# from django.test import TestCase, Client
# from django.urls import reverse
# from forums.models import Forum, Post
# from accounts.models import User
#
# # helper functions
#
#
# def contains(haystack, needle):
#     """This is used to check whether a string (needle) is found in the
#     response.contain (haystack) which is the html file that is returned.  This html
#     file is a binary file so needs to be converted to a string for processing."""
#     return str(haystack).count(needle) > 0
#
#
# def contains_count(haystack, needle):
#     """This is used to the number of times a string (needle) is found in the
#     response.contain (haystack) which is the html file that is returned.  This html
#     file is a binary file so needs to be converted to a string for processing."""
#     return str(haystack).count(needle)
#
#
# # Create your tests here.
# class TestViews(TestCase):
#     def setUp(self):
#         """This sets up each test the same way with the objects that are
#         required"""
#         self.client = Client()
#         self.user = User.objects.create_user(
#             username="john",
#             email="lennon@thebeatles.com",
#             password="johnpassword",
#             system_number=111111,
#         )
#         self.client.login(username="john", password="johnpassword")
#         self.list = reverse("forums:forums")
#         Forum.objects.create(title="testForum", description="testing Forums")
#         self.first_forum = Forum.objects.all().first()
#         Post.objects.create(
#             forum=self.first_forum,
#             title="testPost",
#             summary="testing Post",
#             author_id=1,
#         )
#         self.first_post = Post.objects.all().first()
#
#     # Tests on the list view
#     def test_list_uses_correct_view_with_setup_post(self):
#         response = self.client.get(self.list)
#
#         self.assertEqual(response.status_code, 200)
#         self.assertTemplateUsed(response, "forums/post_list.html")
#         self.assertTrue(contains(response.content, "testPost"))
#         self.assertTrue(contains(response.content, "testForum"))
#
#     def test_list_displays_new_Post_that_has_been_manually_added(self):
#         response = self.client.get(self.list)
#         tally = contains_count(response.content, "testForum")
#
#         Post.objects.create(
#             forum=self.first_forum,
#             title="testPost2",
#             summary="testing Post added manually",
#             author_id=1,
#         )
#         response = self.client.get(self.list)
#
#         self.assertTrue(contains(response.content, "testPost2"))
#         self.assertEqual(tally + 1, contains_count(response.content, "testForum"))
