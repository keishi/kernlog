#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import os
import cgi
import logging
import re
import weakref

import xss
import taggable
import markdown
import paging

from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext.webapp import template
from google.appengine.ext.db import djangoforms

class CachedReferenceProperty(db.ReferenceProperty):
    _cache = weakref.WeakValueDictionary({})
    def __init__(self,
                 reference_class=None,
                 time=0,
                 verbose_name=None,
                 collection_name=None,
                 **attrs):
        super(CachedReferenceProperty, self).__init__(reference_class, verbose_name, collection_name, **attrs)
        self.time = time
    def __id_attr_name(self):
        return self._attr_name()
    def __resolved_attr_name(self):
        return "_RESOLVED"+self._attr_name()
    def __get__(self, model_instance, model_class):
        if model_instance is None:
            return self
        if hasattr(model_instance, self.__id_attr_name()):
            reference_id = getattr(model_instance, self.__id_attr_name())
        else:
            reference_id = None
        if reference_id is not None:
            resolved = getattr(model_instance, self.__resolved_attr_name())
            if resolved is not None:
                return resolved
            else:
                reference_str = str(reference_id)
                instance = CachedReferenceProperty._cache.get(reference_id, None)
                if instance is None:
                    instance = db.get(reference_id)
                    CachedReferenceProperty._cache[reference_id] = instance
                #else:
                #    logging.info("CachedReferenceProperty - found object in cache: "+str(reference_id))
            if instance is None:
                raise Error('ReferenceProperty failed to be resolved')
            setattr(model_instance, self.__resolved_attr_name(), instance)
            return instance
        else:
            return None

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

class Entry(db.Model, taggable.Taggable):
    user_profile = CachedReferenceProperty(UserProfile)
    created_at = db.DateTimeProperty(auto_now_add=True)
    modified_at = db.DateTimeProperty(auto_now=True)
    markdown = db.TextProperty()
    html = db.TextProperty()
    def __init__(self, parent=None, key_name=None, app=None, **entity_values):
        db.Model.__init__(self, parent, key_name, app, **entity_values)
        taggable.Taggable.__init__(self)
    def setMarkdown(self, source):
        self.markdown = source
        tag_names = re.findall(r'\[#(\w+)\]', source)
        tag_names = map(lambda x: x.lower(), tag_names)
        self.tags = tag_names
        cleaner = xss.XssCleaner()
        html = markdown.markdown(self.markdown, ['tables', 'codehilite', 'tagdown', 'mathdown'])
        self.html = cleaner.strip(html)

class LoginHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            current_profile = UserProfile.current_profile()
            if current_profile:
                self.redirect('/home')
            else:
                self.redirect('/signup')
        else:
            self.redirect(users.create_login_url('/login'))

class LogoutHandler(webapp.RequestHandler):
    def get(self):
        self.redirect(users.create_logout_url('/'))

class SignUpForm(djangoforms.django.newforms.Form):
    username = djangoforms.django.newforms.fields.RegexField(required=True, regex=r'[a-z][a-z0-9_]*', min_length=3, max_length=255)
    email = djangoforms.django.newforms.fields.EmailField(required=True)
    name = djangoforms.django.newforms.fields.CharField(max_length=255)
    web = djangoforms.django.newforms.fields.URLField()
    bio = djangoforms.django.newforms.fields.CharField(widget=djangoforms.django.newforms.Textarea)

class SignUpHandler(webapp.RequestHandler):
    def get(self):
        current_user = users.get_current_user()
        if current_user:
            current_profile = UserProfile.current_profile()
            if current_profile:
                self.response.out.write('You are already signed up. %s' % current_profile.username)
            else:
                form = SignUpForm(initial={'initial':users.get_current_user().email()})
                template_values = {
                'current_profile': current_profile,
                'form': form
                }
                path = os.path.join(os.path.dirname(__file__), 'templates/signup.html')
                self.response.out.write(template.render(path, template_values))
        else:
            self.redirect(users.create_login_url('/signup'))
    def post(self):
        current_user = users.get_current_user()
        if current_user:
            current_profile = UserProfile.current_profile()
            if current_profile:
                self.response.out.write('You are already signed up. %s' % current_profile.username)
                return
            else:
                form = SignUpForm(data=self.request.POST)
                if form.is_valid():
                    new_profile = UserProfile()
                    new_profile.username = form.clean_data['username']
                    new_profile.user = current_user
                    new_profile.email = form.clean_data['email']
                    new_profile.name = form.clean_data['name']
                    new_profile.web = form.clean_data['web']
                    new_profile.bio = form.clean_data['bio']
                    new_profile.put()
                    self.redirect('/home')
                else:
                    template_values = {
                    'current_profile': current_profile,
                    'form': form
                    }
                    path = os.path.join(os.path.dirname(__file__), 'templates/signup.html')
                    self.response.out.write(template.render(path, template_values))
        else:
            self.redirect(users.create_login_url('/signup'))

class SettingsForm(djangoforms.django.newforms.Form):
    username = djangoforms.django.newforms.fields.RegexField(required=True, regex=r'[a-z][a-z0-9_]*', min_length=3, max_length=255)
    email = djangoforms.django.newforms.fields.EmailField(required=True)
    name = djangoforms.django.newforms.fields.CharField(max_length=255)
    web = djangoforms.django.newforms.fields.URLField()
    bio = djangoforms.django.newforms.fields.CharField(widget=djangoforms.django.newforms.Textarea)

class SettingsHandler(webapp.RequestHandler):
    def get(self):
        current_profile = UserProfile.current_profile()

        if not current_profile:
            self.redirect("/home")
            return

        form = SettingsForm(initial={'username': current_profile.username, 'email': current_profile.email, 'name': current_profile.name, 'web': current_profile.web, 'bio': current_profile.bio})
        
        template_values = {
        'current_profile': current_profile,
        'form': form
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/settings.html')
        self.response.out.write(template.render(path, template_values))
    def post(self):
        current_profile = UserProfile.current_profile()

        form = SettingsForm(data=self.request.POST)
        if form.is_valid():
            current_profile.username = form.clean_data['username']
            current_profile.email = form.clean_data['email']
            current_profile.name = form.clean_data['name']
            current_profile.web = form.clean_data['web']
            current_profile.bio = form.clean_data['bio']
            current_profile.put()
        template_values = {
        'current_profile': current_profile,
        'form': form
        }
        path = os.path.join(os.path.dirname(__file__), 'templates/settings.html')
        self.response.out.write(template.render(path, template_values))

class PostHandler(webapp.RequestHandler):
    def post(self):
        current_profile = UserProfile.current_profile()
        if not current_profile:
            self.error(401)
            return
        entry = Entry()
        entry.user_profile = current_profile
        entry.put()
        entry.setMarkdown(self.request.get('content'))
        entry.put()
        self.redirect('/home')

class EditHandler(webapp.RequestHandler):
    def get(self, key):
        current_profile = UserProfile.current_profile()
        if not current_profile:
            self.error(401)
            return
        entry = db.get(key)
        if entry.user_profile.key() != current_profile.key():
            self.error(401)
            return
        
        template_values = {
        'current_profile': current_profile,
        'edit_entry': entry,
        'entries': [entry]
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/edit.html')
        self.response.out.write(template.render(path, template_values))
    def post(self, key):
        current_profile = UserProfile.current_profile()
        if not current_profile:
            self.error(401)
            return
        entry = db.get(key)
        if entry.user_profile.key() != current_profile.key():
            self.error(401)
            return
        new_content = self.request.get('content')
        if new_content:
            entry.setMarkdown(new_content)
            entry.put()

        template_values = {
        'current_profile': current_profile,
        'edit_entry': entry,
        'entries': [entry]
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/edit.html')
        self.response.out.write(template.render(path, template_values))

class DeleteHandler(webapp.RequestHandler):
    def get(self, key):
        current_profile = UserProfile.current_profile()
        if not current_profile:
            self.error(401)
            return
        entry = db.get(key)
        if entry.user_profile.key() != current_profile.key():
            self.error(401)
            return
        entry.delete()
        self.redirect('/home')

class ArchiveHandler(webapp.RequestHandler):
    def get(self, username):
        current_profile = UserProfile.current_profile()
        
        if username == 'home':
            person_profile = current_profile
        else:
            person_profile = UserProfile.profile_for_username(username)
        
        page = self.request.get('page')
        if (not page):
            page = 1
        else:
            page = int(page)
        
        entries_per_page = 10
        
        q = Entry.all().filter('user_profile =', person_profile).order('-modified_at')
    	pq = paging.PagedQuery(q, entries_per_page)
        entries = pq.fetch_page(page)
        page_count = pq.page_count()
        
        if page_count > page:
            next_link = '/%s?page=%d' % (username, page + 1)
        else:
            next_link = None
        
        if page > 1:
            prev_link = '/%s?page=%d' % (username, page - 1)
        else:
            prev_link = None
        
        template_values = {
        'current_profile': current_profile,
        'person_profile': person_profile,
        'entries': entries,
        'next_link': next_link,
        'prev_link': prev_link
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/archive.html')
        self.response.out.write(template.render(path, template_values))

class RSSHandler(webapp.RequestHandler):
    def get(self, username):
        current_profile = UserProfile.current_profile()

        if username == 'home':
            person_profile = current_profile
        else:
            person_profile = UserProfile.profile_for_username(username)

        page = 1

        entries_per_page = 10

        q = Entry.all().filter('user_profile =', person_profile).order('-modified_at')
    	pq = paging.PagedQuery(q, entries_per_page)
        entries = pq.fetch_page(page)
        page_count = pq.page_count()

        template_values = {
        'current_profile': current_profile,
        'person_profile': person_profile,
        'entries': entries,
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/rss.xml')
        self.response.out.write(template.render(path, template_values))

class TagHandler(webapp.RequestHandler):
    def get(self, username, tag_name):
        current_profile = UserProfile.current_profile()

        tag_name = tag_name.lower()

        if username == 'tag':
            person_profile = None
        elif username == 'home':
            person_profile = current_profile
        else:
            person_profile = UserProfile.profile_for_username(username)

        page = self.request.get('page')
        if (not page):
            page = 1
        else:
            page = int(page)

        entries_per_page = 10

        tag = taggable.Tag.get_by_name(tag_name)
        q = Entry.all().filter('__key__ IN', tag.tagged)
        if person_profile:
            # cursor does not support MultiQuery so we fall back.
            q.filter('user_profile =', person_profile)
            page_count = int(q.count() / entries_per_page + 0.5)
            offset = (page - 1) * entries_per_page
            entries = q.fetch(entries_per_page, offset)
        else:
            pq = paging.PagedQuery(q, entries_per_page)
            entries = pq.fetch_page(page)
            page_count = pq.page_count()

        if page_count > page:
            next_link = '/%s?page=%d' % (username, page + 1)
        else:
            next_link = None

        if page > 1:
            prev_link = '/%s?page=%d' % (username, page - 1)
        else:
            prev_link = None

        template_values = {
        'current_profile': current_profile,
        'person_profile': person_profile,
        'tag': tag_name,
        'entries': entries,
        'next_link': next_link,
        'prev_link': prev_link
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/tag.html')
        self.response.out.write(template.render(path, template_values))

class SingleEntryHandler(webapp.RequestHandler):
    def get(self, key):
        current_profile = UserProfile.current_profile()

        entry = db.get(key)
        entries = [entry]

        template_values = {
        'current_profile': current_profile,
        'entries': entries,
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/home.html')
        self.response.out.write(template.render(path, template_values))

class AboutHandler(webapp.RequestHandler):
    def get(self):
        current_profile = UserProfile.current_profile()
        
        template_values = {
        'current_profile': current_profile
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/about.html')
        self.response.out.write(template.render(path, template_values))

class MainHandler(webapp.RequestHandler):
    def get(self):
        current_profile = UserProfile.current_profile()

        entries_per_page = 10
        q = Entry.gql('ORDER BY modified_at DESC')
        entry_count = q.count()
        page_count = int(entry_count / entries_per_page + 0.5)
        entries = q.fetch(entries_per_page)

        template_values = {
        'current_profile': current_profile,
        'entries': entries,
        }

        path = os.path.join(os.path.dirname(__file__), 'templates/public.html')
        self.response.out.write(template.render(path, template_values))


def real_main():
    application = webapp.WSGIApplication([('/', MainHandler), ('/about', AboutHandler), ('/login', LoginHandler), ('/logout', LogoutHandler), 
    ('/signup', SignUpHandler), ('/post', PostHandler), ('/settings', SettingsHandler), ('/entry/(.+)', SingleEntryHandler), 
    ('/edit/(.+)', EditHandler), ('/delete/(.+)', DeleteHandler), ('/([a-z][a-z0-9_]*)', ArchiveHandler), 
    ('/([a-z][a-z0-9_]*)/rss', RSSHandler), ('/([a-z][a-z0-9_]*)/(\w+)', TagHandler)],
                                         debug=True)
    util.run_wsgi_app(application)

import traceback
from google.appengine.api import apiproxy_stub_map

def profile_datastore():
    def hook(service, call, request, response):
        logging.info('%s %s - %s' % (service, call, str(request)))
        stack = traceback.format_stack()
        logging.debug('%s %s - %s' % (service, call, "n".join(stack)))

    apiproxy_stub_map.apiproxy.GetPreCallHooks().Append('db_log', hook, 'datastore_v3')

def profile_main():
    #profile_datastore()
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    print "<pre>"
    stats = pstats.Stats(prof)
    stats.sort_stats("time")  # Or cumulative
    stats.print_stats(80)  # 80 = how many to print
    # The rest is optional.
    # stats.print_callees()
    # stats.print_callers()
    print "</pre>"

if __name__ == '__main__':
    #main = profile_main
    main = real_main
    main()
