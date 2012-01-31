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

SELECT_POST = 'SELECT * FROM Posted WHERE link = ?'
INSERT_CONTROL = 'INSERT INTO Control (id,last_update) VALUES (?,?)'
#INSERT_FEED = 'INSERT INTO Feeds (title,link,created,updated) VALUES (?,?,?,?)'

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
    
    def __execute_sql(self, query, params):
        self.log.debug("%s, %s" % (query, params))
        self.cursor.execute(query, params)
        
    def __get_last_update(self, id_, url):
        self.log.debug('Looking for the last update')
        self.__execute_sql(SELECT_LAST_UPDATE, (id_, url))
        rtn = self.cursor.fetchone()
        if rtn is None:
            self.log.debug('No record for last update')
            return rtn
        else:
            #last_update = rtn[0]
            last_update = '20110502-1715'
        return last_update
        
    def __set_last_update(self, id_, url):
        self.log.debug('Setting last update for %s' % url)
        values = (time.strftime('%Y%m%d-%H%M'), id_, url)
        self.cursor.execute(UPDATE_LAST_UPDATE, values)
        self.connection.commit()
        return values[0]
    
    def __get_all_feeds(self):
        self.cursor.execute(SELECT_ALL_FEEDS)
        feeds = self.cursor.fetchall()
        return [Feed(obj) for obj in feeds]
    
    def add_feed(self, url):
        self.log.debug('Adding feed %s' % url)
        self.cursor.execute(SELECT_FEED, (url, ))
        if self.cursor.fetchone():
            self.log.info('Feed already exist in database')
        else:
            self.cursor.execute(INSERT_FEED, (url, ))
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
        self.cursor.execute(DELETE_FEED, (id_,))
        self.connection.commit()
        if self.cursor.rowcount > 0:
            self.log.info('Feed removed successfully')
        else:
            self.log.info('That feed was not found in database')
        
    def main(self):
        while True:
            try:
                worked = False
                new_posts = []
                feeds = self.__get_all_feeds()
                for feed in feeds:
                    self.log.debug('Processing %s' % feed.url)
                    
                    # Reading the last_update flag
                    last_update = self.__get_last_update(feed.id_, feed.url)
                    to_process = []
                    d = feedparser.parse(feed.url)
                    self.log.debug('Processing RSS for "%s"', d.feed.title)
                    for item in d.entries:
                        created = time.strftime("%Y%m%d-%H%M", item.published_parsed)
                        updated = time.strftime("%Y%m%d-%H%M", item.updated_parsed)
                        
                        if last_update is None:
                            if len(to_process) < MAX_POST_PER_FEED:
                                to_process.append(item)
                            else:
                                break
                        else:
                            if created < last_update:
                                if updated < last_update:
                                    print 'too old', item.title
                                    continue
                            to_process.append(item)
                    
                    # Saving the last_update flag
                    self.__set_last_update(feed.id_, feed.url)
                    print to_process
                    # TODO: Search for feed on database, if it doesn't exist
                    # then publish it on twitter and add it to database
                    
                    #FIND_FEED
                    #self.log.debug('Processing entry for "%s"', item.title)
                    #data = (item.title, item.link, created, updated)
                    #self.cursor.execute(INSERT_NEW_FEED, update)
                
                
                time.sleep(POLLING_TIME * 60)
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
        
if __name__ == "__main__":
    t = TwitRss()
    t.main()
