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
import feedparser

from optparse import OptionParser

POLLING_TIME = 5 #min
RSS_FEED = 'http://damncorner.blogspot.com/feeds/posts/default'

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
    
    def main(self):
        d = feedparser.parse(RSS_FEED)
        self.log.debug('Processing RSS for %s', d.feed.title)
        for item in d.entries:
            print "Title:", item.title
            print "Link:", item.link
            print "Published:", time.strftime("%d-%M-%Y", item.published_parsed)
            print "Updateed:", time.strftime("%d-%M-%Y", item.updated_parsed)
        '''
        while True:
            try:
                
                time.sleep(POLLING_TIME * 60)
            except KeyboardInterrupt:
                break
        self.log.debug('Bye')
        '''

if __name__ == "__main__":
    t = TwitRss()
    t.main()
