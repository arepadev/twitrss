#!/usr/bin/python2
# -*- coding: utf-8 -*-

""" Twitter bot based on libturpial that reads RSS feeds and tweet them on 
configured accounts """

# Authors: 
#   * Wil Alvarez (aka Satanas)
# Organization: ArepaDev <http://github.com/arepadev>
# Jan 26, 2012

import time
import logging
import sqlite3
import feedparser

from optparse import OptionParser

POLLING_TIME = 5 #min
RSS_FEED = 'http://damncorner.blogspot.com/feeds/posts/default'
FIND_FEED = 'SELECT * FROM Feeds WHERE link = ?'
INSERT_NEW_CONTROL = 'INSERT INTO Control (id,last_update) VALUES (?,?)'
INSERT_NEW_FEED = 'INSERT INTO Feeds (title,link,created,updated) VALUES (?,?,?,?)'

class TwitRss:
    def __init__(self):
        parser = OptionParser()
        parser.add_option('-d', '--debug', dest='debug', action='store_true',
            help='show debug info in shell during execution', default=False)
        
        (options, args) = parser.parse_args()
        
        if options.debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
        
        self.log = logging.getLogger('TwitRSS')
        self.log.debug("Starting")
        
        self.log.debug("Setting up database connection")
        self.connection = sqlite3.connect('database.db')
        self.cursor = self.connection.cursor()
    
    def __get_last_update(self):
        self.cursor.execute('SELECT * FROM Control WHERE id = 1')
        rtn = self.cursor.fetchone()
        if rtn is None:
            self.log.debug('No record for last update. Creating a new one')
            update = (1, time.strftime('%Y%m%d-%H%M'))
            self.cursor.execute(INSERT_NEW_CONTROL, update)
            self.connection.commit()
            self.last_update = update[1]
        else:
            self.last_update = rtn[1]
        self.last_update = '20110502-1715'
    
    def __set_last_update(self):
        self.log.debug('Setting last update')
        update = (time.strftime('%Y%m%d-%H%M'), 1)
        self.cursor.execute('UPDATE Control SET last_update = ? WHERE id = ?', update)
        self.connection.commit()
        self.last_update = update[0]
        
    def main(self):
        while True:
            try:
                worked = False
                self.__get_last_update()
                
                d = feedparser.parse(RSS_FEED)
                self.log.debug('Processing RSS for "%s"', d.feed.title)
                for item in d.entries:
                    created = time.strftime("%Y%m%d-%H%M", item.published_parsed)
                    updated = time.strftime("%Y%m%d-%H%M", item.updated_parsed)
                    
                    if created < self.last_update:
                        if updated < self.last_update:
                            continue
                    
                    # TODO: Search for feed on database, if it doesn't exist
                    # then publish it on twitter and add it to database
                    
                    #FIND_FEED
                    #self.log.debug('Processing entry for "%s"', item.title)
                    #data = (item.title, item.link, created, updated)
                    #self.cursor.execute(INSERT_NEW_FEED, update)
                
                
                time.sleep(POLLING_TIME * 60)
            except KeyboardInterrupt:
                break
        self.connection.close()
        self.log.debug('Bye')
        

if __name__ == "__main__":
    t = TwitRss()
    t.main()
