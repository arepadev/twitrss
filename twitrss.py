#!/usr/bin/python2
# -*- coding: utf-8 -*-

""" Twitter bot based on libturpial that reads RSS feeds and tweet them on 
configured accounts """

# Authors: 
#   * Wil Alvarez (aka Satanas)
# Organization: ArepaDev <http://github.com/arepadev>
# Jan 26, 2012

import sys
import time
import Queue
import getpass
import logging
import sqlite3
import feedparser

from optparse import OptionParser

from libturpial.api.core import Core
from libturpial.common import ProtocolType

POSTING_TIME = 1 # min
POLLING_TIME = 5 # min
MAX_POST_PER_FEED = 5

#RSS_FEED = 'http://damncorner.blogspot.com/feeds/posts/default'

# Queries
SELECT_ALL_FEEDS = 'SELECT * FROM Feeds'
SELECT_FEED = 'SELECT * FROM Feeds WHERE url = ?'
INSERT_FEED = 'INSERT INTO Feeds (url) VALUES (?)'
DELETE_FEED = 'DELETE FROM Feeds WHERE id = ?'
SELECT_LAST_UPDATE = 'SELECT last_update FROM Feeds WHERE id = ? and url = ?'
UPDATE_LAST_UPDATE = 'UPDATE Feeds SET last_update = ? WHERE id = ? AND url = ?'

SELECT_POST = 'SELECT * FROM Posted WHERE link = ?  '
INSERT_POST = 'INSERT INTO Posted (title,link,created,updated) VALUES (?,?,?,?)'

class TwitRss:
    def __init__(self):
        parser = OptionParser()
        parser.add_option('-d', '--debug', dest='debug', action='store_true',
            help='show debug info in shell during execution', default=False)
        parser.add_option('--add-feed', dest='feed_to_add',
            help='add a feed to database')
        parser.add_option('--list-feeds', dest='list_feeds', 
            action='store_true', help='list all feeds', default=False)
        parser.add_option('--remove-feed', dest='feed_to_remove',
            help='remove a feed to database')
        parser.add_option('--add-account', dest='add_account', 
            action='store_true', help='add a microblogging account to database')
        parser.add_option('--delete-account', dest='delete_account', 
            action='store_true', help='delete a microblogging account from \
            database')
        
        (options, args) = parser.parse_args()
        
        if options.debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
        
        self.log = logging.getLogger('TwitRSS')
        self.log.debug("Setting up database connection")
        self.connection = sqlite3.connect('database.db')
        self.cursor = self.connection.cursor()
        
        if options.feed_to_add:
            self.add_feed(options.feed_to_add)
            self.quit()
            
        if options.feed_to_remove:
            self.remove_feed(options.feed_to_remove)
            self.quit()
        
        if options.list_feeds:
            self.list_feeds()
            self.quit()
        
        self.log.info("Starting service")
        self.queue = Queue.Queue()
        self.core = Core()
        
        if options.add_account:
            self.add_account()
            self.quit()
        
        if options.delete_account:
            self.delete_account()
            self.quit()
        
        self.start_login()
        
    def __execute_sql(self, query, params=None):
        self.log.debug("%s, %s" % (query, params))
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
    
    def __user_input(self, message, blank=False):
        while 1:
            text = raw_input(message)
            if text == '' and not blank:
                print "You can't leave this field blank"
                continue
            break
        return text
    
    def __user_password(self, message):
        passwd = None
        while 1:
            passwd = getpass.unix_getpass(message)
            if passwd:
                return passwd
            else:
                print "Password can't be blank"
                
    def __build_protocols_menu(self):
        index = None
        protocols = self.core.list_protocols()
        while 1:
            print "Available protocols:"
            for i in range(len(protocols)):
                print "[%i] %s" % (i, protocols[i])
            index = raw_input('Select protocol: ')
            if not self.__validate_index(index, protocols):
                print "Invalid protocol"
            else:
                break
        return protocols[int(index)]
    
    def __build_accounts_menu(self, _all=False):
        if len(self.core.list_accounts()) == 1: 
            return self.core.list_accounts()[0]
        
        index = None
        while 1:
            accounts = self.__show_accounts()
            if _all:
                index = raw_input('Select account (or Enter for all): ')
            else:
                index = raw_input('Select account: ')
            if not self.__validate_index(index, accounts, _all):
                print "Invalid account"
            else:
                break
        if index == '':
            return ''
        else:
            return accounts[int(index)]
    
    def __show_accounts(self):
        if len(self.core.list_accounts()) == 0:
            print "There are no registered accounts"
            return
        
        accounts = []
        print "Available accounts:"
        for acc in self.core.list_accounts():
            print "[%i] %s - %s" % (len(accounts), acc.split('-')[0], 
                acc.split('-')[1])
            accounts.append(acc)
        return accounts
    
    def __validate_index(self, index, array, blank=False):
        try:
            a = array[int(index)]
            return True
        except IndexError:
            return False
        except ValueError:
            if blank and index == '':
                return True
            elif not blank and index == '':
                return False
            elif blank and index != '':
                return False
        except TypeError:
            if index is None:
                return False
    
    def __get_last_update(self, id_, url):
        self.log.debug('Looking for the last update')
        self.__execute_sql(SELECT_LAST_UPDATE, (id_, url))
        rtn = self.cursor.fetchone()
        if rtn is None:
            self.log.debug('No record for last update')
            return rtn
        else:
            return rtn[0]
            #return '20110502-1715'
        
    def __set_last_update(self, id_, url):
        self.log.debug('Setting last update for %s' % url)
        values = (time.strftime('%Y%m%d-%H%M'), id_, url)
        self.__execute_sql(UPDATE_LAST_UPDATE, values)
        self.connection.commit()
        return values[0]
    
    def __get_all_feeds(self):
        self.__execute_sql(SELECT_ALL_FEEDS)
        feeds = self.cursor.fetchall()
        return [Feed(obj) for obj in feeds]
    
    def __enqueue_post(self, post):
        self.__execute_sql(SELECT_POST, (post.link, ))
        rtn = self.cursor.fetchone()
        print rtn
        if rtn is None:
            data = (post.title, post.link, post.created_at, post.updated_at)
            self.__execute_sql(INSERT_POST, data)
            self.connection.commit()
            if self.cursor.rowcount > 0:
                self.log.debug('Enqueued post %s', post.link)
                self.queue.put(post)
            else:
                self.log.info('Post not enqueued %s', post.link)
    
    def start_login(self):
        accounts = self.core.all_accounts()
        for acc in accounts:
            self.core.register_account(acc.username, acc.protocol_id)
            response = self.core.login(acc.id_)
            if response.code > 0:
                print "Login error:", response.errmsg
                return
            
            auth_obj = response.items
            if auth_obj.must_auth():
                print "Please visit %s, authorize Turpial and type the pin \
                    returned" % auth_obj.url
                pin = self.user_input('Pin: ')
                self.core.authorize_oauth_token(acc.id_, pin)
            
            rtn = self.core.auth(acc.id_)
            if rtn.code > 0:
                print rtn.errmsg
            else:
                self.log.debug('Logged in with account %s' % acc.id_)
        
        self.main()
    
    # =======================================================================
    # Commands
    # =======================================================================
    
    def add_feed(self, url):
        self.log.debug('Adding feed %s' % url)
        self.__execute_sql(SELECT_FEED, (url, ))
        if self.cursor.fetchone():
            self.log.info('Feed already exist in database')
        else:
            self.__execute_sql(INSERT_FEED, (url, ))
            self.connection.commit()
            self.log.info('Feed added successfully')
    
    def list_feeds(self):
        self.log.debug('Listing feeds')
        feeds = self.__get_all_feeds()
        if len(feeds) > 0:
            print '  ID   URL'
            print '=' * 80
            for feed in feeds:
                print "%4s   %s" % (feed.id_, feed.url)
        else:
            self.log.info('There are no feeds registered')
    
    def remove_feed(self, id_):
        self.log.debug('Removing feed with id %s' % id_)
        self.__execute_sql(DELETE_FEED, (id_,))
        self.connection.commit()
        if self.cursor.rowcount > 0:
            self.log.info('Feed removed successfully')
        else:
            self.log.info('That feed was not found in database')
    
    def add_account(self):
        username = self.__user_input('Username: ')
        protocol = self.__build_protocols_menu()
        passwd = ''
        if protocol == ProtocolType.IDENTICA:
            passwd = self.__user_password('Password: ')
        try:
            self.core.register_account(username, protocol, passwd)
            self.log.info('Account added successfully')
        except Exception, e:
            self.log.exception(e)
            self.log.error('Error registering account. Please try again')
    
    def delete_account(self):
        account = self.__build_accounts_menu()
        try:
            self.core.unregister_account(account, True)
            self.log.info('Account deleted successfully')
        except Exception, e:
            self.log.exception(e)
            self.log.error('Error deleting account. Please try again')
    
    # =======================================================================
    # Services
    # =======================================================================
    
    def polling(self):
        feeds = self.__get_all_feeds()
        for feed in feeds:
            self.log.debug('Processing %s' % feed.url)
            
            # Reading the last_update flag
            last_update = self.__get_last_update(feed.id_, feed.url)
            
            # Preparing the process vars
            d = feedparser.parse(feed.url)
            self.log.debug('Processing RSS for "%s"', d.feed.title)
            for item in d.entries:
                post = Post(item)
                if last_update is None:
                    if len(to_process) < MAX_POST_PER_FEED:
                        self.__enqueue_post(post)
                    else:
                        break
                else:
                    if post.older_than(last_update):
                        continue
                    self.__enqueue_post(post)
            
            # Saving the last_update flag
            self.__set_last_update(feed.id_, feed.url)
    
    def posting(self):
        try:
            post = self.queue.get(False)
        except Queue.Empty:
            return
        except:
            return
        url = self.core.short_url(post.link)
        message = "[Post] %s - %s" % (post.title, url)
        if len(message) > 140:
            title = post.title[:len(message) - 144] + '...'
            message = "[Post] %s - %s" % (title, url)
        
        print message
        # TODO: Tuitear
        # TODO: Guardar en la base de datos
        # TODO: En caso de error meter el post de nuevo en la cola
    
    def main(self):
        count_posting = 1
        count_polling = 1
        while True:
            try:
                if count_polling > POLLING_TIME:
                    self.polling()
                    count_polling = 0
                
                if count_posting > POSTING_TIME:
                    self.posting()
                    count_posting = 0
                
                time.sleep(5)
                count_posting += 1
                count_polling += 1
            except KeyboardInterrupt:
                break
            
        self.quit()
    
    def quit(self, error=False):
        self.connection.close()
        self.log.debug('Bye')
        if error:
            sys.exit(-1)
        sys.exit(0)
        
class Feed:
    def __init__(self, db_object):
        self.id_ = db_object[0]
        self.url = db_object[1]
        self.last_update = db_object[2]

class Post:
    def __init__(self, entry):
        self.title = entry.title
        self.link = entry.link
        self.created_at = time.strftime("%Y%m%d-%H%M", entry.published_parsed)
        self.updated_at = time.strftime("%Y%m%d-%H%M", entry.updated_parsed)
    
    def __str__(self):
        return "%s: %s (%s - %s)" % (self.title, self.link, self.created_at,
            self.updated_at)
    
    def older_than(self, value):
        if self.created_at < value and self.updated_at < value:
            return True
        return False
        
if __name__ == "__main__":
    t = TwitRss()
