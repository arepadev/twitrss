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
import logging
import sqlite3
import feedparser

from optparse import OptionParser

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
        parser.add_option('-a', '--add-feed', dest='feed_to_add',
            help='add a feed to database')
        parser.add_option('-l', '--list-feeds', dest='list_feeds', 
            action='store_true', help='list all feeds', default=False)
        parser.add_option('-r', '--remove-feed', dest='feed_to_remove',
            help='remove a feed to database')
        
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
    
    def __execute_sql(self, query, params=None):
        self.log.debug("%s, %s" % (query, params))
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
            
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
        print post
    
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
    t.main()
