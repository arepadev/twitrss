#!/usr/bin/python2
# -*- coding: utf-8 -*-

""" Twitter bot based on libturpial that reads RSS feeds and post them on 
microblogging accounts """

# Authors: 
#   * Wil Alvarez (aka Satanas)
# Organization: ArepaDev <http://github.com/arepadev>
# Jan 26, 2012

import os
import sys
import time
import Queue
import shutil
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

# Queries
SELECT_ALL_FEEDS = 'SELECT * FROM Feeds'
SELECT_FEED_BY_ID = 'SELECT * FROM Feeds WHERE id = ?'
SELECT_FEED_BY_URL = 'SELECT * FROM Feeds WHERE url = ?'
INSERT_FEED = 'INSERT INTO Feeds (url) VALUES (?)'
DELETE_FEED = 'DELETE FROM Feeds WHERE id = ?'
SELECT_LAST_UPDATE = 'SELECT last_update FROM Feeds WHERE id = ? and url = ?'
UPDATE_LAST_UPDATE = 'UPDATE Feeds SET last_update = ? WHERE id = ? AND url = ?'

SELECT_ACCOUNT_BY_CODE = 'SELECT * FROM Accounts WHERE code = ?'
SELECT_ACCOUNT_BY_ID = 'SELECT * FROM Accounts WHERE id = ?'
INSERT_ACCOUNT = 'INSERT INTO Accounts (username,protocol,code) VALUES (?,?,?)'
DELETE_ACCOUNT = 'DELETE FROM Accounts WHERE id = ?'

SELECT_ALL_ACCOUNT_FEEDS = 'SELECT * FROM AccountFeeds'
SELECT_ACCOUNT_FEED = """
SELECT AccountFeeds.id, Feeds.id, Accounts.id, AccountFeeds.prefix
FROM AccountFeeds 
LEFT JOIN Accounts ON Accounts.id=AccountFeeds.account_id 
LEFT JOIN Feeds ON Feeds.id=AccountFeeds.feed_id 
WHERE Feeds.id = ?
"""
SELECT_ACCOUNT_FEED_2 = """
SELECT Accounts.username, Accounts.protocol, Accounts.code 
FROM AccountFeeds 
LEFT JOIN Accounts ON Accounts.id=AccountFeeds.account_id 
LEFT JOIN Feeds ON Feeds.id=AccountFeeds.feed_id 
WHERE Feeds.id = ? AND Accounts.id = ?
"""
INSERT_ACCOUNT_FEED = """
INSERT INTO AccountFeeds (feed_id,account_id,prefix) 
VALUES (?,?,?)
"""
DELETE_ACCOUNT_FEED = 'DELETE FROM AccountFeeds WHERE id = ?'
DELETE_ACCOUNT_FEED_BY_ACCOUNT = 'DELETE FROM AccountFeeds WHERE account_id = ?'
DELETE_ACCOUNT_FEED_BY_FEED = 'DELETE FROM AccountFeeds WHERE feed_id = ?'

SELECT_POST = 'SELECT * FROM Posts WHERE link = ?'
INSERT_POST = """
INSERT INTO Posts (title,link,created,updated,account_id) VALUES (?,?,?,?,?)
"""
DELETE_POST_BY_ACCOUNT = 'DELETE FROM Posts WHERE account_id = ?'

# TODO: Test menues with no accounts, no feeds and no associations
# TODO: Initialize with current date for posting none at first run

class TwitRss:
    def __init__(self):
        parser = OptionParser()
        parser.add_option('-d', '--debug', dest='debug', action='store_true',
            help='show debug info in shell during execution', default=False)
        parser.add_option('--setup', dest='setup', action='store_true',
            help='execute the setup wizard', default=False)
        parser.add_option('--add-account', dest='add_account', default=False,
            action='store_true', help='add a microblogging account to database')
        parser.add_option('--del-account', dest='delete_account', 
            action='store_true', help='delete a microblogging account from \
            database', default=False)
        parser.add_option('--list-accounts', dest='list_accounts', 
            action='store_true', help='list all microblogging accounts', 
            default=False)
        
        parser.add_option('--add-feed', dest='add_feed', action='store_true',
            help='add feed to database', default=False)
        parser.add_option('--del-feed', dest='delete_feed', action='store_true',
            help='delete feed from database', default=False)
        parser.add_option('--list-feeds', dest='list_feeds', 
            action='store_true', help='list all registered feeds', 
            default=False)
        
        parser.add_option('--associate', dest='associate_feed', 
            action='store_true', help='associate feed with account', 
            default=False)
        parser.add_option('--deassociate', dest='deassociate_feed', 
            action='store_true', help='deassociate feed from account', 
            default=False)
        
        parser.add_option('--change-prefix', dest='change_prefix', 
            action='store_true', default=False,
            help='change the publish prefix for certain feed/account')
        
        parser.add_option('--show-info', dest='show_info', action='store_true',
            help='show information about feeds and accounts', default=False)
        
        (options, args) = parser.parse_args()
        
        if options.debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
        
        self.log = logging.getLogger('TwitRSS')
        self.db = DBEngine()
        Feed.db = self.db
        Account.db = self.db
        AccountFeed.db = self.db
        Post.db = self.db
        self.core = Core()
        Account.core = self.core
        
        if options.setup:
            self.setup()
            self.quit()
        
        if options.add_account:
            self.add_account()
            self.quit()
        
        if options.delete_account:
            self.delete_account()
            self.quit()
        
        if options.add_feed:
            self.add_feed()
            self.quit()
            
        if options.delete_feed:
            self.delete_feed()
            self.quit()
        
        if options.associate_feed:
            self.associate_feed()
            self.quit()
        
        if options.deassociate_feed:
            self.deassociate_feed()
            self.quit()
        
        if options.show_info:
            self.show_info()
            self.quit()
        
        self.log.info("Starting service")
        self.queue = Queue.Queue()
        Post.queue = self.queue
        self.start_login()
    
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
    
    def __build_confirm_menu(self, message):
        confirm = raw_input(message + ' [y/N]: ')
        if confirm.lower() == 'y':
            return True
        else:
            return False
    
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
            return accounts
        else:
            return accounts[int(index)]
    
    def __show_accounts(self, just_list=False):
        accounts = []
        reg_accs = Account.get_from_libturpial()
        
        if len(reg_accs) == 0:
            return None
        
        print "\nAvailable accounts:"
        for acc in reg_accs:
            if just_list:
                print "* %s (%s)" % (acc.username, acc.protocol)
            else:
                print "[%i] %s - %s" % (len(accounts), acc.username, 
                    acc.protocol)
            full_acc = Account.save_from_obj(acc)
            accounts.append(full_acc)
        return accounts
    
    def __build_feeds_menu(self):
        index = None
        while 1:
            feeds = self.__show_feeds()
            index = raw_input('Select feed: ')
            if not self.__validate_index(index, feeds, False):
                print "Invalid feed"
            else:
                break
        return feeds[int(index)]
        
    def __show_feeds(self, just_list=False):
        rtn = Feed.get_all()
        
        if len(rtn) == 0:
            self.log.info("There are no registered feeds")
            return None
        
        feeds = []
        
        print "\nAvailable feeds:"
        for feed in rtn:
            if just_list:
                print "* %s" % (feed.url)
            else:
                print "[%i] %s" % (len(feeds), feed.url)
            feeds.append(feed)
        return feeds
    
    def __build_account_feeds_menu(self):
        index = None
        while 1:
            afs = self.__show_account_feeds()
            index = raw_input('Select account/feed: ')
            if not self.__validate_index(index, afs, False):
                print "Invalid account/feed"
            else:
                break
        return afs[int(index)]
    
    def __show_account_feeds(self, just_list=False):
        rtn = AccountFeed.get_all()
        
        if len(rtn) == 0:
            self.log.info("There are no feeds associated with accounts")
            return None
        
        account_feeds = []
        
        print "\nFeeds associated with accounts:"
        for af in rtn:
            if just_list:
                print "* %-35s %-35s" % (af.account, af.feed.url)
            else:
                print "[%i] %-35s %-35s" % (len(account_feeds), af.account, 
                    af.feed.url)
            account_feeds.append(af)
        return account_feeds
    
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
    
    def setup(self):
        accounts = self.__show_accounts(True)
        if not accounts:
            print 'You need to create at least one account'
            self.add_account()
            
        while 1:
            if self.__build_confirm_menu('Do you want to add more accounts?'):
                self.add_account()
            else:
                break
        
        self.__show_feeds(True)
        while 1:
            if self.__build_confirm_menu('Do you want to add more feeds?'):
                self.add_feed()
            else:
                break
        
        while 1:
            if self.__build_confirm_menu('\nDo you want to associate feeds with accounts?'):
                self.associate_feed()
            else:
                break
    
    def add_account(self):
        username = self.__user_input('Username: ')
        protocol = self.__build_protocols_menu()
        passwd = ''
        if protocol == ProtocolType.IDENTICA:
            passwd = self.__user_password('Password: ')
        try:
            acc_id = self.core.register_account(username, protocol, passwd)
            response = self.core.login(acc_id)
            if response.code > 0:
                self.log.error(response.errmsg)
                return
            
            auth_obj = response.items
            if auth_obj.must_auth():
                print "Please visit %s, authorize Turpial and type the pin returned" % auth_obj.url
                pin = self.__user_input('Pin: ')
                self.core.authorize_oauth_token(acc_id, pin)
            
            rtn = self.core.auth(acc_id)
            if rtn.code > 0:
                self.log.error(response.errmsg)
                return
            
            # Save in DB
            Account.save(acc_id, username, protocol)
            self.log.info('Account added successfully')
        except Exception, e:
            self.log.exception(e)
            self.log.error('Error registering account. Please try again')
    
    def add_feed(self):
        url = self.__user_input('URL: ')
        if Feed.get_by_url(url):
            self.log.info('Feed already exist in database')
        else:
            Feed.save(url)
            self.log.info('Feed registered successfully')
    
    def associate_feed(self):
        feed = self.__build_feeds_menu()
        afs = AccountFeed.get_by_feed_id(feed.id_)
        count = len(afs)
        
        if count == Account.count():
            print 'This feed has been associated to all your accounts'
        else:
            if count == 0:
                print 'You must to associate this feed with at least one account'
            else:
                print "This feed has been associated with:"
                for item in afs:
                    print "* %s (%s)" % (item.account.username, 
                        item.account.protocol)
                if not self.__build_confirm_menu('Do you want to associate this feed to another account?'):
                    return
            print 
            rtn = self.__build_accounts_menu(_all=True)
            if isinstance(rtn, list):
                for acc in rtn:
                    exist = False
                    for item in afs:
                        if item.account.code == acc.code:
                            exist = True
                            break
                    if not exist:
                        prefix = self.__user_input('Type the prefix for posting in %s account: ' % acc, True)
                        AccountFeed.save(acc, feed.id_, prefix)
            else:
                for item in afs:
                    if item.account.code == rtn.code:
                        self.log.info('This feed already has been associated with that account')
                        return
                prefix = self.__user_input('Type the prefix for posting in %s account: ' % rtn, True)
                AccountFeed.save(rtn, feed.id_, prefix)
            
            self.log.info('Feed associated successfully')
    
    def delete_feed(self):
        feed = self.__build_feeds_menu()
        try:
            AccountFeed.delete_by_feed(feed.id_)
            Feed.delete(feed.id_)
            self.log.info('Feed deleted successfully')
        except Exception, e:
            self.log.exception(e)
            self.log.error('Error deleting feed. Please try again')
    
    def delete_account(self):
        account = self.__build_accounts_menu()
        try:
            self.core.unregister_account(account.code, True)
            Post.delete_by_account(account.id_)
            AccountFeed.delete_by_account(account.id_)
            Account.delete(account.id_)
            self.log.info('Account deleted successfully')
        except Exception, e:
            self.log.exception(e)
            self.log.error('Error deleting account. Please try again')
    
    def deassociate_feed(self):
        af = self.__build_account_feeds_menu()
        try:
            AccountFeed.delete(af.id_)
            self.log.info('Account deassociated from Feed successfully')
        except Exception, e:
            self.log.exception(e)
            self.log.error('Error deassociating account form feed. Please try again')
        
    def list_feeds(self):
        self.log.debug('Listing feeds')
        feeds = self.__get_all_feeds()
        count = len(feeds)
        if count > 0:
            print '  ID   URL'
            print '=' * 80
            for feed in feeds:
                print "%4s   %s" % (feed.id_, feed.url)
        else:
            self.log.info('There are no feeds registered')
        return count
    
    def show_info(self):
        self.__show_feeds(just_list=True)
        self.__show_accounts(just_list=True)
        self.__show_account_feeds(just_list=True)
    
    # =======================================================================
    # Services
    # =======================================================================
    
    def polling(self):
        self.log.debug('Polling...')
        to_process = 0
        feeds = Feed.get_all()
        for feed in feeds:
            # Preparing the process vars
            d = feedparser.parse(feed.url)
            self.log.debug('Processing RSS for "%s" (%s)' % (d.feed.title, 
                feed.url))
            
            entries = d.entries
            if feed.last_update is None:
                entries = d.entries[:MAX_POST_PER_FEED]
            entries.reverse()
            for item in entries:
                post = Post(item, feed)
                if feed.last_update and post.older_than(feed.last_update):
                    continue
                post.enqueue()
                to_process += 1
            
            self.log.debug('Setting last update for %s' % feed.url)
            feed.updated()
    
    def posting(self):
        self.log.debug('Posting...') 
        try:
            post = self.queue.get(False)
        except Queue.Empty:
            self.log.debug('Nothing to post') 
            return
        except:
            return
        
        url = post.url
        response = self.core.short_url(url)
        if response.code == 0:
            url = response.items
        
        accounts = []
        for afs in post.account_feeds:
            accounts.append(afs.account.code)
            title = post.title
            max_length = 140 - len(afs.prefix)
            message = "%s - %s" % (title, url)
            
            if len(message) > max_length:
                title = post.title[:len(message) - max_length] + '...'
            
            message = "%s - %s" % (title, url)
            
            if afs.prefix != '':
                message = "%s %s" % (afs.prefix, message)
            
        print message
        # self.core.broadcast_status(accounts, message)
        # post.save()
        # TODO: En caso de error meter el post de nuevo en la cola
    
    # =======================================================================
    # Main Loop
    # =======================================================================
    
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
        self.db.connection.close()
        self.log.debug('Bye')
        if error:
            sys.exit(-1)
        sys.exit(0)

class DBEngine:
    def __init__(self):
        self.log = logging.getLogger('DB')
        if not os.path.isfile('database.db'):
            shutil.copy('empty_database.db', 'database.db')
        self.log.debug("Setting up database connection")
        self.connection = sqlite3.connect('database.db')
        self.cursor = self.connection.cursor()
        
    def execute(self, query, params=None, commit=False):
        #self.log.debug("%s, %s" % (query, params))
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        if commit:
            self.connection.commit()
    
class Feed:
    def __init__(self, db_object):
        self.id_ = db_object[0]
        self.url = db_object[1]
        if db_object[2] == '':
            self.last_update = None
        else:
            self.last_update = db_object[2]
    
    @classmethod
    def get_all(self):
        self.db.execute(SELECT_ALL_FEEDS)
        feeds = self.db.cursor.fetchall()
        return [Feed(obj) for obj in feeds]
    
    @classmethod
    def get_by_url(self, url):
        self.db.execute(SELECT_FEED_BY_URL, (url, ))
        rtn = self.db.cursor.fetchone()
        if rtn:
            return Feed(rtn)
        else:
            return None
    
    @classmethod
    def get_by_id(self, id_):
        self.db.execute(SELECT_FEED_BY_ID, (id_, ))
        rtn = self.db.cursor.fetchone()
        if rtn:
            return Feed(rtn)
        else:
            return None
    
    @classmethod
    def save(self, url):
        self.db.execute(INSERT_FEED, (url, ), True)
    
    @classmethod
    def delete(self, id_):
        self.db.execute(DELETE_FEED, (id_, ), True)
    
    def updated(self):
        values = (time.strftime('%Y%m%d-%H%M'), self.id_, self.url)
        self.db.execute(UPDATE_LAST_UPDATE, values, True)
    
class Account:
    def __init__(self, code, username, protocol, id_=None):
        self.id_ = id_
        self.code = code
        self.username = username
        self.protocol = protocol
    
    def __str__(self):
        return "%s (%s)" % (self.username, self.protocol)
    
    @classmethod
    def get_all(self):
        pass
    
    @classmethod
    def get_by_id(self, id_):
        self.db.execute(SELECT_ACCOUNT_BY_ID, (id_, ))
        obj = self.db.cursor.fetchone()
        if obj:
            return Account(obj[3], obj[1], obj[2], obj[0])
        else:
            return None
    
    @classmethod
    def get_by_code(self, code):
        self.db.execute(SELECT_ACCOUNT_BY_CODE, (code, ))
        obj = self.db.cursor.fetchone()
        if obj:
            return Account(obj[3], obj[1], obj[2], obj[0])
        else:
            return None
    
    @classmethod
    def get_from_libturpial(self):
        accounts = []
        for acc in self.core.list_accounts():
            accounts.append(Account(acc, acc.split('-')[0], acc.split('-')[1]))
        return accounts
    
    @classmethod
    def save(self, code, username, protocol):
        rtn = self.get_by_code(code)
        if rtn is None:
            self.db.execute(INSERT_ACCOUNT, (username, protocol, code), True)
        
    @classmethod
    def save_from_obj(self, obj):
        rtn = self.get_by_code(obj.code)
        if rtn:
            return rtn
        else:
            self.save(obj.code, obj.username, obj.protocol)
            return self.get_by_code(obj.code)
    
    @classmethod
    def count(self):
        return len(self.core.list_accounts())
    
    @classmethod
    def delete(self, id_):
        self.db.execute(DELETE_ACCOUNT, (id_, ), True)
    
class AccountFeed:
    def __init__(self, id_, feed, account, prefix=''):
        self.id_ = id_
        self.feed = feed
        self.account = account
        self.prefix = prefix
    
    @classmethod
    def get_all(self):
        self.db.execute(SELECT_ALL_ACCOUNT_FEEDS)
        account_feeds = []
        afs = self.db.cursor.fetchall()
        for obj in afs:
            feed = Feed.get_by_id(obj[1])
            account = Account.get_by_id(obj[2])
            account_feeds.append(AccountFeed(obj[0], feed, account, obj[3]))
        return account_feeds
    
    @classmethod
    def get_by_feed_id(self, feed_id):
        feed = Feed.get_by_id(feed_id)
        self.db.execute(SELECT_ACCOUNT_FEED, (feed_id, ))
        results = []
        for item in self.db.cursor.fetchall():
            account = Account.get_by_id(item[2])
            results.append(AccountFeed(item[0], feed, account, item[3]))
        return results
    
    @classmethod
    def exist(self, account_id, feed_id):
        self.db.execute(SELECT_ACCOUNT_FEED_2, (feed_id, account_id))
        return self.db.cursor.fetchone()
        
    @classmethod
    def save(self, account, feed_id, prefix):
        if self.exist(account.id_, feed_id):
            self.log.info('This feed already has been associated with that account')
            return
        self.db.execute(INSERT_ACCOUNT_FEED, (feed_id, account.id_, prefix), 
            True)
    
    @classmethod
    def delete(self, id_):
        self.db.execute(DELETE_ACCOUNT_FEED, (id_, ), True)
        
    @classmethod
    def delete_by_account(self, acc_id):
        self.db.execute(DELETE_ACCOUNT_FEED_BY_ACCOUNT, (acc_id, ), True)
    
    @classmethod
    def delete_by_feed(self, feed_id):
        self.db.execute(DELETE_ACCOUNT_FEED_BY_FEED, (feed_id, ), True)
        
class Post:
    def __init__(self, entry, feed):
        self.feed = feed
        self.title = entry.title
        self.url = entry.link
        self.created_at = time.strftime("%Y%m%d-%H%M", entry.published_parsed)
        self.updated_at = time.strftime("%Y%m%d-%H%M", entry.updated_parsed)
        self.account_feeds = AccountFeed.get_by_feed_id(feed.id_)
        
    def __str__(self):
        return "%s: %s (%s - %s)" % (self.title, self.url, self.created_at,
            self.updated_at)
    
    def older_than(self, value):
        if self.created_at < value and self.updated_at < value:
            return True
        return False
    
    @classmethod
    def delete_by_account(self, acc_id):
        self.db.execute(DELETE_POST_BY_ACCOUNT, (acc_id, ), True)
    
    @classmethod
    def is_in_database(self, url):
        self.db.execute(SELECT_POST, (url, ))
        return self.db.cursor.fetchone()
    
    def enqueue(self):
        if not Post.is_in_database(self.url):
            self.queue.put(self)
    
    def save(self):
        data = (self.title, self.url, self.created_at, self.updated_at, '')
        self.db.execute(INSERT_POST, data, True)

if __name__ == "__main__":
    t = TwitRss()
