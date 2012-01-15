#!/usr/bin/python

# Code stolen from totem plugin
# Should add here the correct licence, credits and everything

import gobject
gobject.threads_init()
import xmlrpclib
import sys
import os
import glob
import gettext
import gio
import threading
from optparse import OptionParser
from hash import hashFile

D_ = gettext.dgettext

USER_AGENT = 'Totem'
OK200 = '200 OK'
DEST = ""
MEDIA_EXT = [
    ".avi",
    ".mkv",
    ".mp4",
]


class DownloadThread(threading.Thread):
    def __init__(self, model, subtitles, choice, filename):
        self.model = model
        self.subtitles = subtitles
        self.choice = choice
        self.filename = filename
        self._done = False
        self._lock = threading.Lock()
        threading.Thread.__init__(self)

    def run(self):
        self.model.lock.acquire(True)
        self.model.download_subtitles(self.subtitles, self.choice, self.filename)
        self.model.lock.release()
        self._done = True
    
    @property
    def done(self):
        """ Thread-safe property to know whether the query is done or not """
        self._lock.acquire(True)
        res = self._done
        self._lock.release()
        return res


class GetSubModel():
    def __init__(self):
        self.server = xmlrpclib.Server('http://api.opensubtitles.org/xml-rpc')
        self.username = ''
        self.password = ''
        self.message = ''
        self.token = None
        self.hash = None
        self.size = 0
        self.lock = threading.Lock()
        self.DEST = None
        self.LANG = None
        
    def log_in(self):
        # already logged ?
        if self.token:
            try:
                result = self.server.NoOperation(self.token)
            except:
                pass
            if result and result['status'] == OK200:
                return True
        try: 
            isLogged = self.server.LogIn(self.username, self.password, self.LANG, USER_AGENT)
        except:
            pass
        if isLogged and isLogged['status'] == OK200:
            self.token = isLogged['token']
            if self.token:
                return True
        
        self.message = 'Cannot contact opensubtitle.org'
        
        return False
        
    def search_subtitles(self, filename):
        
        self.message = ''
        self.hash, self.size = hashFile(filename)
        
        if self.log_in():
            searchdata = {'sublanguageid': self.LANG, 
                          'moviehash'    : self.hash, 
                          'moviebytesize': str(self.size)}
            
            try:
                result = self.server.SearchSubtitles(self.token, [searchdata])
            except xmlrpclib.ProtocolError:
                self.message = 'Could not contact the OpenSubtitles website'

            if result['data']:
                return result['data']
            else:
                self.message = 'No results found'

        return None

    def get_subtitleId_from_subtitle(self, subtitles, index):
        return subtitles[index-1]['IDSubtitleFile']
    
    def get_subFormat_from_subtitle(self, subtitles, index):
        return subtitles[index-1]['SubFormat']
        
    def download_subtitles(self, subtitles, choice, filename):
        self.message = ''
        
        if choice == '0':
            return
            
        subtitleId = self.get_subtitleId_from_subtitle(subtitles, choice)
        subtitleFormat = self.get_subFormat_from_subtitle(subtitles, choice)
                
        if self.log_in():
            try:
                result = self.server.DownloadSubtitles(self.token, [subtitleId])
            except xmlrpclib.ProtocolError:
                self.message = 'Could not contact the OpenSubtitles website'

            if result and result.get('status') == OK200:
                try:
                    subtitle64 = result['data'][0]['data']
                except:
                    self.message = 'Could not contact the OpenSubtitles website'
                    return None

                import StringIO, gzip, base64
                subtitleDecoded = base64.decodestring(subtitle64)
                subtitleGzipped = StringIO.StringIO(subtitleDecoded)
                subtitleGzippedFile = gzip.GzipFile(fileobj=subtitleGzipped)
                
                fp = gio.File(self.DEST + filename[:-3] + subtitleFormat)
                subFile = fp.replace('', False)
                subFile.write(subtitleGzippedFile.read())
                subFile.close()

        return None


class GetSubView():
    def __init__(self):
        pass
            
    def print_sub_filename(self, subtitle):
        if subtitle == None:
            return
        print '\n'
        i = 1
        for sub in subtitle:
            print '['+str(i)+'] '+ sub['SubFileName']
            i += 1
        
        print '[0] No one'

class GetSubController:
    def __init__(self):
        self.model = GetSubModel()
        self.view = GetSubView()
        
        self.choice = None
        self.subtitles = None
        
    def search_subtitles(self, filename):
        self.subtitles = self.model.search_subtitles(filename)
        self.view.print_sub_filename(self.subtitles)    

    def choose_subtitles(self):
        if self.subtitles:
            self.choice = int(raw_input('Select your subtitle file : '))
        else:
            print '\n'+self.model.message
            self.choice = 0
            
            
    
    def download_subtitles(self, filename):
        if self.choice and self.subtitles:
            self.model.download_subtitles(self.subtitles, self.choice, filename)
            #thread = DownloadThread(self.model, self.subtitles, self.choice, filename)
            #thread.start()
            
def main():
    usage = "usage: %prog [option] arg"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    parser.add_option("-f", "--file", dest="filename", help="filename of the file you want to get the subtitles")
    parser.add_option("-d", "--dir", dest="directory", help="directory that contains every files you want to get the subtitles")
    parser.add_option("-l", "--language", dest="LANG", help="language in which you want to download subtitles (french is default)")
    parser.add_option("-D", "--destination", dest="DEST", help="the directory where you want to download your subtitles")
    
    (options, args) = parser.parse_args()
    
    directory = options.directory
    filename = options.filename
    
    controller = GetSubController()    
    
    if options.LANG:
        controller.model.LANG = options.LANG
    else:
        controller.model.LANG = 'fre'
    
    DEST = options.DEST
    if DEST:
        if os.path.isdir(DEST):
            if DEST[:-1] != '/':
                DEST = DEST + '/'
            controller.model.DEST = DEST
    else:
        controller.model.DEST = ''    
    if directory != None:
        medias = [os.path.normcase(f)
                    for f in os.listdir(directory)]
        medias = [os.path.join(directory, f) 
                   for f in medias
                    if os.path.splitext(f)[1] in MEDIA_EXT]
                    
        for media in medias:
            controller.search_subtitles(media)
            controller.choose_subtitles()
            controller.download_subtitles(media)            
    elif filename != None:
        controller.search_subtitles(filename)
        controller.choose_subtitles()
        controller.download_subtitles(filename) 
    
if __name__ == "__main__":
    main() 
