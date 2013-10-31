import sys
import time
import re
import urllib2
from BeautifulSoup import BeautifulSoup
from html2text import html2text

class Bug:
    """A Redmine bug needing exporting to Bugzilla"""

    _base = 'http://redmine.yorba.org'

    # TODO: do these change with viewer/server prefs?
    _timestamp_re = re.compile(r'\d\d/\d\d/\d\d\d\d \d\d:\d\d (?:a|p)m')
    _timestamp_format = '%m/%d/%Y %I:%M %p'

    def __init__(self, bug_id):
        self.bug_id = bug_id

    def scrape(self):
        """Returns a dictionary of information about the bug"""

        def _s(tag, lower=False):
            s = unicode(tag.string)
            if s == '-':
                return None
            if lower:
                return s.lower()
            return s

        url = '{0}/issues/{1}'.format(Bug._base, self.bug_id)
        html = BeautifulSoup(urllib2.urlopen(url).read(), convertEntities=BeautifulSoup.HTML_ENTITIES)
        # TODO: remove img tags before anything else happens
        issue = html('div', 'issue')[0]
        author = issue('p', 'author')[0]
        times = author('a', title=Bug._timestamp_re)
        attributes = issue('table', 'attributes')[0]

        data = {}
        data['title'] = _s(issue('div', 'subject')[0].h3)
        data['author'] = _s(author.a)
        data['assignee'] = _s(attributes('td', 'assigned-to')[0].a)
        data['created'] = time.strptime(times[0]['title'], Bug._timestamp_format)
        data['updated'] = time.strptime(times[1]['title'], Bug._timestamp_format)
        data['status'] = _s(attributes('td', 'status')[0], True)
        data['priority'] = _s(attributes('td', 'priority')[0], True)
        data['category'] = _s(attributes('td', 'category')[0], True)
        data['version'] = _s(attributes('td', 'fixed-version')[0], True)
        data['description'] = html2text(unicode(issue('div', 'wiki')[0])).strip()
        data['history'] = html2text(unicode(html('div', id='history')[0])).strip()
        return data

class Bugzilla:
    """A Bugzilla database receiving exported Redmine bugs"""

def main(argv=None):
    if argv is None:
        argv = sys.argv

    b = Bug(7649)
    print b.scrape()

    return 0

if __name__ == '__main__':
    sys.exit(main())
