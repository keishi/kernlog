from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.tools import bulkloader

class UserProfile(db.Model):
    username = db.StringProperty()
    user = db.UserProperty()
    email = db.EmailProperty()
    created_at = db.DateTimeProperty(auto_now_add=True)
    name = db.StringProperty()
    web = db.LinkProperty()
    bio = db.StringProperty()
    @classmethod
    def profile_for_username(self, username):
        return UserProfile.gql('WHERE username = :1', username).get()
    @classmethod
    def profile_for_user(self, user):
        return UserProfile.gql('WHERE user = :1', user).get()
    @classmethod
    def current_profile(self):
        return UserProfile.profile_for_user(users.get_current_user())

class Entry(db.Model):
    user_profile = db.ReferenceProperty(UserProfile)
    created_at = db.DateTimeProperty(auto_now_add=True)
    modified_at = db.DateTimeProperty(auto_now=True)
    markdown = db.TextProperty()
    html = db.TextProperty()

class EntryLoader(bulkloader.Loader):
  def __init__(self):
    bulkloader.Loader.__init__(self, 'Entry',
                               [('markdown', str),
                                ('html', str)])

loaders = [EntryLoader]