from ..interfaces import IConversation
from ..testing import PLONE_APP_DISCUSSION_INTEGRATION_TESTING
from Acquisition import aq_base
from persistent.list import PersistentList
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from plone.base.interfaces import IMailSchema
from plone.registry.interfaces import IRegistry
from Products.MailHost.interfaces import IMailHost
from Products.MailHost.MailHost import _mungeHeaders
from Products.MailHost.MailHost import MailBase
from zope.component import createObject
from zope.component import getSiteManager
from zope.component import getUtility
from zope.component import queryUtility

import unittest


class MockMailHost(MailBase):
    """A MailHost that collects messages instead of sending them."""

    def __init__(self, id):
        self.reset()

    def reset(self):
        self.messages = PersistentList()

    def _send(self, mfrom, mto, messageText, immediate=False):
        """Send the message"""
        self.messages.append(messageText)

    def send(
        self,
        messageText,
        mto=None,
        mfrom=None,
        subject=None,
        encode=None,
        immediate=False,
        charset=None,
        msg_type=None,
    ):
        """send *messageText* modified by the other parameters.

        *messageText* can either be an ``email.message.Message``
        or a string.
        Note that Products.MailHost 4.10 had changes here.
        """
        msg, mto, mfrom = _mungeHeaders(
            messageText, mto, mfrom, subject, charset, msg_type, encode
        )
        self.messages.append(msg)


class TestUserNotificationUnit(unittest.TestCase):

    layer = PLONE_APP_DISCUSSION_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        # Set up a mock mailhost
        self.portal._original_MailHost = self.portal.MailHost
        self.portal.MailHost = mailhost = MockMailHost("MailHost")
        sm = getSiteManager(context=self.portal)
        sm.unregisterUtility(provided=IMailHost)
        sm.registerUtility(mailhost, provided=IMailHost)
        # We need to fake a valid mail setup
        registry = getUtility(IRegistry)
        mail_settings = registry.forInterface(IMailSchema, prefix="plone")
        mail_settings.email_from_address = "portal@plone.test"
        self.mailhost = self.portal.MailHost
        # Enable user notification setting
        registry = queryUtility(IRegistry)
        registry[
            "plone.app.discussion.interfaces.IDiscussionSettings"
            + ".user_notification_enabled"
        ] = True
        self.portal.doc1.title = "Kölle Alaaf"  # What is 'Fasching'?
        self.conversation = IConversation(self.portal.doc1)

    def beforeTearDown(self):
        self.portal.MailHost = self.portal._original_MailHost
        sm = getSiteManager(context=self.portal)
        sm.unregisterUtility(provided=IMailHost)
        sm.registerUtility(aq_base(self.portal._original_MailHost), provided=IMailHost)

    def test_notify_user(self):
        # Add a comment with user notification enabled. Add another comment
        # and make sure an email is send to the user of the first comment.
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.user_notification = True
        comment.author_email = "john@plone.test"
        self.conversation.addComment(comment)
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        comment_id = self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 1)
        self.assertTrue(self.mailhost.messages[0])
        msg = self.mailhost.messages[0]
        msg = msg.decode("utf-8")
        self.assertIn("To: john@plone.test", msg)
        self.assertIn("From: portal@plone.test", msg)
        # We expect the headers to be properly header encoded (7-bit):
        self.assertIn("Subject: =?utf-8?q?A_comment_has_been_posted=2E?=", msg)
        # The output should be encoded in a reasonable manner
        # (in this case quoted-printable).
        # Depending on which Python version and which Products.MailHost version,
        # you may get lines separated by '\n' or '\r\n' in here.
        msg = msg.replace("\r\n", "\n")
        self.assertIn('A comment on "K=C3=B6lle Alaaf" has been posted here:', msg)
        self.assertIn(f"http://nohost/plone/d=\noc1/view#{comment_id}", msg)
        self.assertIn("Comment text", msg)
        self.assertNotIn("Approve comment", msg)
        self.assertNotIn("Delete comment", msg)

    def test_do_not_notify_user_when_notification_is_disabled(self):
        registry = queryUtility(IRegistry)
        registry[
            "plone.app.discussion.interfaces.IDiscussionSettings."
            + "user_notification_enabled"
        ] = False
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.user_notification = True
        comment.author_email = "john@plone.test"
        self.conversation.addComment(comment)
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 0)

    def test_do_not_notify_user_when_email_address_is_given(self):
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.user_notification = True
        self.conversation.addComment(comment)
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 0)

    def test_do_not_notify_user_when_no_sender_is_available(self):
        # Set sender mail address to none and make sure no email is send to
        # the moderator.
        registry = getUtility(IRegistry)
        mail_settings = registry.forInterface(IMailSchema, prefix="plone")
        mail_settings.email_from_address = None
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.user_notification = True
        comment.author_email = "john@plone.test"
        self.conversation.addComment(comment)
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        self.conversation.addComment(comment)
        self.assertEqual(len(self.mailhost.messages), 0)

    def test_notify_only_once(self):
        # When a user has added two comments in a conversation and has
        # both times requested email notification, do not send him two
        # emails when another comment has been added.
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.user_notification = True
        comment.author_email = "john@plone.test"
        self.conversation.addComment(comment)
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.user_notification = True
        comment.author_email = "john@plone.test"

        self.conversation.addComment(comment)

        # Note that we might want to get rid of this message, as the
        # new comment is added by the same user.
        self.assertEqual(len(self.mailhost.messages), 1)
        self.mailhost.reset()
        self.assertEqual(len(self.mailhost.messages), 0)


class TestModeratorNotificationUnit(unittest.TestCase):

    layer = PLONE_APP_DISCUSSION_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        # Set up a mock mailhost
        self.portal._original_MailHost = self.portal.MailHost
        self.portal.MailHost = mailhost = MockMailHost("MailHost")
        sm = getSiteManager(context=self.portal)
        sm.unregisterUtility(provided=IMailHost)
        sm.registerUtility(mailhost, provided=IMailHost)
        # We need to fake a valid mail setup
        registry = getUtility(IRegistry)
        mail_settings = registry.forInterface(IMailSchema, prefix="plone")
        mail_settings.email_from_address = "portal@plone.test"
        self.mailhost = self.portal.MailHost
        # Enable comment moderation
        self.portal.portal_types["Document"].allow_discussion = True
        self.portal.portal_workflow.setChainForPortalTypes(
            ("Discussion Item",),
            ("comment_review_workflow",),
        )
        # Enable moderator notification setting
        registry = queryUtility(IRegistry)
        registry[
            "plone.app.discussion.interfaces.IDiscussionSettings."
            + "moderator_notification_enabled"
        ] = True
        self.portal.doc1.title = "Kölle Alaaf"  # What is 'Fasching'?
        self.conversation = IConversation(self.portal.doc1)

    def beforeTearDown(self):
        self.portal.MailHost = self.portal._original_MailHost
        sm = getSiteManager(context=self.portal)
        sm.unregisterUtility(provided=IMailHost)
        sm.registerUtility(aq_base(self.portal._original_MailHost), provided=IMailHost)

    def test_notify_moderator(self):
        """Add a comment and make sure an email is send to the moderator."""
        comment = createObject("plone.Comment")
        comment.text = "Comment text"
        comment.author_email = "john@plone.test"

        comment_id = self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 1)
        self.assertTrue(self.mailhost.messages[0])
        msg = self.mailhost.messages[0]
        msg = msg.decode("utf-8")
        self.assertTrue("To: portal@plone.test" in msg)
        self.assertTrue("From: portal@plone.test" in msg)
        # We expect the headers to be properly header encoded (7-bit):
        self.assertTrue("Subject: =?utf-8?q?A_comment_has_been_posted=2E?=" in msg)
        # The output should be encoded in a reasonable manner
        # (in this case quoted-printable):
        self.assertTrue('A comment on "K=C3=B6lle Alaaf" has been posted' in msg)
        self.assertIn(f"http://nohost/plone/doc1/view#{comment_id}", msg)
        self.assertIn(comment.author_email, msg)
        self.assertIn(comment.text, msg)

    def test_notify_moderator_specific_address(self):
        # A moderator email address can be specified in the control panel.
        registry = queryUtility(IRegistry)
        registry[
            "plone.app.discussion.interfaces.IDiscussionSettings" + ".moderator_email"
        ] = "test@example.com"
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 1)
        msg = self.mailhost.messages[0]
        msg = msg.decode("utf-8")
        self.assertTrue("To: test@example.com" in msg)

    def test_do_not_notify_moderator_when_no_sender_is_available(self):
        # Set sender mail address to nonw and make sure no email is send to the
        # moderator.
        registry = getUtility(IRegistry)
        mail_settings = registry.forInterface(IMailSchema, prefix="plone")
        mail_settings.email_from_address = None
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 0)

    def test_do_not_notify_moderator_when_notification_is_disabled(self):
        # Disable moderator notification setting and make sure no email is send
        # to the moderator.
        registry = queryUtility(IRegistry)
        registry[
            "plone.app.discussion.interfaces.IDiscussionSettings."
            + "moderator_notification_enabled"
        ] = False
        comment = createObject("plone.Comment")
        comment.text = "Comment text"

        self.conversation.addComment(comment)

        self.assertEqual(len(self.mailhost.messages), 0)
