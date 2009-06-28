import unittest
from datetime import datetime, timedelta

from plone.registry import Registry

from zope.component import createObject

from Acquisition import aq_base, aq_parent, aq_inner

from OFS.Image import Image

from plone.app.vocabularies.types import BAD_TYPES

from Products.CMFCore.FSImage import FSImage
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.tests import dummy
from Products.PloneTestCase.ptc import PloneTestCase

from plone.app.discussion.browser.moderation import View
from plone.app.discussion.interfaces import IConversation, IComment, IReplies, IDiscussionSettings
from plone.app.discussion.tests.layer import DiscussionLayer


class ModerationViewTest(PloneTestCase):

    layer = DiscussionLayer

    def afterSetUp(self):
        self.loginAsPortalOwner()
        typetool = self.portal.portal_types
        typetool.constructContent('Document', self.portal, 'doc1')
        self.portal_discussion = getToolByName(self.portal, 'portal_discussion', None)
        self.membership_tool = getToolByName(self.folder, 'portal_membership')
        self.memberdata = self.portal.portal_memberdata
        request = self.app.REQUEST
        context = getattr(self.portal, 'doc1')
        self.view = View(context, request)
        self.portal.portal_workflow.setChainForPortalTypes(('Discussion Item',), 'comment_review_workflow')
        self.wf_tool = self.portal.portal_workflow

        # Add a conversation with three comments

        conversation = IConversation(self.portal.doc1)

        comment1 = createObject('plone.Comment')
        comment1.title = 'Comment 1'
        comment1.text = 'Comment text'
        comment1.Creator = 'Jim'
        new_id_1 = conversation.addComment(comment1)
        self.comment1 = self.portal.doc1.restrictedTraverse('++conversation++default/%s' % new_id_1)

        comment2 = createObject('plone.Comment')
        comment2.title = 'Comment 2'
        comment2.text = 'Comment text'
        comment2.Creator = 'Joe'
        new_id_2 = conversation.addComment(comment2)
        self.comment2 = self.portal.doc1.restrictedTraverse('++conversation++default/%s' % new_id_2)

        comment3 = createObject('plone.Comment')
        comment3.title = 'Comment 3'
        comment3.text = 'Comment text'
        comment3.Creator = 'Emma'
        new_id_3 = conversation.addComment(comment3)
        self.comment3 = self.portal.doc1.restrictedTraverse('++conversation++default/%s' % new_id_3)

    def test_comments_all(self):
        self.failUnless(self.view.comments_all())
        self.assertEquals(len(self.view.comments_all()), 3)

    def test_comments_pending(self):
        self.wf_tool.getInfoFor(self.comment1, 'review_state')
        self.failUnless(self.view.comments_pending())
        self.assertEquals(len(self.view.comments_pending()), 3)
        self.portal.portal_workflow.doActionFor(self.comment1, action='publish')
        #self.comment1.reindexObject()
        #self.assertEquals(len(self.view.comments_pending()), 2)

    def test_comments_published(self):
        self.assertEquals(len(self.view.comments_published()), 0)
        self.wf_tool.doActionFor(self.comment1, action='publish')
        #self.assertEquals(len(self.view.comments_published()), 1)

    def test_comments_spam(self):
        self.view.comments_spam()

def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)