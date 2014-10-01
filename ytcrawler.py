#!/usr/bin/env python

from pafy import Pafy
import sys
from urllib import urlencode
import collections
import logging
from urllib2 import build_opener, HTTPError, URLError
import time
from json import load
from urllib2 import urlopen
import re
import math
from urllib import urlencode
uni, byt, xinput = unicode, str, raw_input
uni = unicode

utf8_encode = lambda x: x.encode("utf8") if type(x) == uni else x
utf8_decode = lambda x: x.decode("utf8") if type(x) == byt else x

def fmt_time(seconds):
    """ Format number of seconds to %H:%M:%S. """

    hms = time.strftime('%H:%M:%S', time.gmtime(int(seconds)))
    H, M, S = hms.split(":")

    if H == "00":
        hms = M + ":" + S

    elif H == "01" and int(M) < 40:
        hms = uni(int(M) + 60) + ":" + S

    elif H.startswith("0"):
        hms = ":".join([H[1], M, S])

    return hms
    
    
class Playlist(object):

    """ Representation of a playist, has list of songs. """

    def __init__(self, name=None, songs=None):
        self.name = name
        self.creation = time.time()
        self.songs = songs or []

    @property
    def is_empty(self):
        """ Return True / False if songs are populated or not. """

        return bool(not self.songs)

    @property
    def size(self):
        """ Return number of tracks. """

        return len(self.songs)

    @property
    def duration(self):
        """ Sum duration of the playlist. """

        duration = sum(s.length for s in self.songs)
        duration = time.strftime('%H:%M:%S', time.gmtime(int(duration)))
        return duration
 
        
def yt_datetime(yt_date_time):
    """ Return a time object and locale formated date string. """

    time_obj = time.strptime(yt_date_time, "%Y-%m-%dT%H:%M:%S.000Z")
    locale_date = time.strftime("%x", time_obj)
    # strip first two digits of four digit year
    short_date = re.sub(r"(\d\d\D\d\d\D)20(\d\d)$", r"\1\2", locale_date)
    return time_obj, short_date
  
    
def num_repr(num):
    """ Return up to four digit string representation of a number, eg 2.6m. """

    if num <= 9999:
        return uni(num)

    digit_count = lambda x: int(math.floor(math.log10(x)) + 1)
    digits = digit_count(num)
    sig = 3 if digits % 3 == 0 else 2
    rounded = int(round(num, int(sig - digits)))
    digits = digit_count(rounded)
    suffix = "_kmBTqXYX"[(digits - 1) // 3]
    front = 3 if digits % 3 == 0 else digits % 3

    if not front == 1:
        return uni(rounded)[0:front] + suffix

    return uni(rounded)[0] + "." + uni(rounded)[1] + suffix
    
        
class ConfigItem(object):

    """ A configuration item. """

    def __init__(self, name, value, minval=None, maxval=None, check_fn=None):
        """ If specified, the check_fn should return a dict.

        {valid: bool, message: success/fail mesage, value: value to set}

        """

        self.default = self.value = value
        self.name = name
        self.type = type(value)
        self.maxval, self.minval = maxval, minval
        self.check_fn = check_fn
        self.require_known_player = False
        self.allowed_values = []

    @property
    def get(self):
        """ Return value. """

        return self.value

    @property
    def display(self):
        """ Return value in a format suitable for display. """

        retval = self.value

        if self.name == "max_res":
            retval = uni(retval) + "p"

        return retval

    def set(self, value):
        """ Set value with checks. """

        # note: fail_msg should contain %s %s for self.name, value
        #       success_msg should not
        # pylint: disable=R0912
        # too many branches

        success_msg = fail_msg = ""
        value = value.strip()
        value_orig = value
        green = lambda x: "%s%s%s" % (c.g, x, c.w)

        # handle known player not set

        if self.allowed_values and not value in self.allowed_values:
            fail_msg = "%s must be one of * - not %s"
            fail_msg = fail_msg.replace("*", ", ".join(self.allowed_values))

        if self.require_known_player and not known_player_set():
            fail_msg = "%s requires mpv or mplayer, can't set to %s"

        # handle true / false values

        elif self.type == bool:

            if value.upper() in "0 OFF NO DISABLED FALSE".split():
                value = False
                success_msg = "%s set to False" % green(self.name)

            elif value.upper() in "1 ON YES ENABLED TRUE".split():
                value = True
                success_msg = "%s set to True" % green(self.name)

            else:
                fail_msg = "%s requires True/False, got %s"

        # handle int values

        elif self.type == int:

            if not value.isdigit():
                fail_msg = "%s requires a number, got %s"

            else:
                value = int(value)

                if self.maxval and self.minval:

                    if not self.minval <= value <= self.maxval:
                        m = " must be between %s and %s, got "
                        m = m % (self.minval, self.maxval)
                        fail_msg = "%s" + m + "%s"

                if not fail_msg:
                    dispval = value or "None"
                    success_msg = "%s set to %s" % (green(self.name), dispval)

        # handle space separated list

        elif self.type == list:
            success_msg = "%s set to %s" % (green(self.name), value)
            value = value.split()

        # handle string values

        elif self.type == str:
            dispval = value or "None"
            success_msg = "%s set to %s" % (green(self.name), green(dispval))

        # handle failure

        if fail_msg:
            failed_val = value_orig.strip() or "<nothing>"
            colvals = c.y + self.name + c.w, c.y + failed_val + c.w
            return fail_msg % colvals

        elif self.check_fn:
            checked = self.check_fn(value)
            value = checked.get("value") or value

            if checked['valid']:
                value = checked.get("value", value)
                self.value = value
                saveconfig()
                return checked.get("message", success_msg)

            else:
                return checked.get('message', fail_msg)

        elif success_msg:
            self.value = value
            saveconfig()
            return success_msg

 
class Config(object):

    """ Holds various configuration values. """

    ORDER = ConfigItem("order", "relevance")
    ORDER.allowed_values = "relevance date views rating".split()
    MAX_RESULTS = ConfigItem("max_results", 19, maxval=50, minval=1)
    
    
def generate_search_qs(term, page):
    """ Return query string. """

    aliases = dict(relevance="relevance", date="published", rating="rating",
                   views="viewCount")
    term = utf8_encode(term)
    qs = {
        'q': term,
        'v': 2,
        'alt': 'jsonc',
        'start-index': ((page - 1) * Config.MAX_RESULTS.get + 1) or 1,
        'safeSearch': "none",
        #'max-results': Config.MAX_RESULTS.get,
        'paid-content': "false",
        'orderby': aliases[Config.ORDER.get]
    }
    return qs
        
         
def get_tracks_from_json(jsons):
        """ Get search results from web page. """

        try:
         items = jsons['data']['items']

        except KeyError:
         items = []

        songs = []
        item = items[0]
        
        url = "https://www.youtube.com/watch?v="+item['id']
        video = Pafy(url)
        
        print "-------------------------"
        print "Title: %s" % item['title']
        print "Uploader: %s" % item['uploader']
        print "Category: %s" % item['category']
        print "Duration: %s" % fmt_time(item['duration'])
        print "Description: %s" % video.description
        print "Keywords:" 
        for keyword in video.keywords:
           print keyword
        print "-------------------------"

        if not items:
          dbg("got unexpected data or no search results")
          return False

        return songs
        

def _search(url, progtext, qs=None, splash=True, pre_load=False):
     url = url + "?" + urlencode(qs) if qs else url
     try:
            response = urlopen(url)
            json_obj = load(response)
            songs = get_tracks_from_json(json_obj)
 
     except (URLError, HTTPError) as e:
            print "error"
            
     return True
     
       
def search(term, page=1, splash=True):
    #term = "Carly Rae Jepsen - OFF SESSION - Tug Of War"
    original_term = term
    logging.info("search for %s", original_term)
    url = "https://gdata.youtube.com/feeds/api/videos"
    query = generate_search_qs(term, page)
    _search(url, original_term, query)

        
       
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
       print >> sys.stderr, 'SYNTAX: test.py [video title]'
       sys.exit(-1)

    search(' '.join(args), 1, True)

