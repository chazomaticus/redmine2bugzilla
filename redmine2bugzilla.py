import sys
import time
import re
import urllib2
from BeautifulSoup import BeautifulSoup
from html2text import html2text

redmine_base = 'http://redmine.yorba.org'

# TODO: do these change with viewer/server prefs?
timestamp_re = re.compile(r'\d\d/\d\d/\d\d\d\d \d\d:\d\d (?:a|p)m')
timestamp_format = '%m/%d/%Y %I:%M %p'

href_ignore_re = re.compile(r'^(?!https?://)')

def scrape(bug_id):
    """Returns a dictionary of information about the bug"""

    def to_s(tag, lower=False):
        s = unicode(tag.string)
        if s == '-':
            return None
        if lower:
            return s.lower()
        return s

    def to_text(tag):
        [img.extract() for img in tag('img')]
        [a.replaceWith(a.string) for a in tag('a', href=href_ignore_re)]
        return html2text(unicode(tag)).strip()

    url = '{0}/issues/{1}'.format(redmine_base, bug_id)
    html = BeautifulSoup(urllib2.urlopen(url).read(), convertEntities=BeautifulSoup.HTML_ENTITIES)
    issue = html('div', 'issue')[0]
    author = issue('p', 'author')[0]
    times = author('a', title=timestamp_re)
    attributes = issue('table', 'attributes')[0]
    assignee = attributes('td', 'assigned-to')[0]

    data = {}
    data['title'] = to_s(issue('div', 'subject')[0].h3)
    data['author'] = to_s(author.a)
    data['assignee'] = to_s(assignee.a if assignee.a != None else assignee)
    data['created'] = time.strptime(times[0]['title'], timestamp_format)
    data['updated'] = time.strptime(times[1]['title'], timestamp_format)
    data['status'] = to_s(attributes('td', 'status')[0], True)
    data['priority'] = to_s(attributes('td', 'priority')[0], True)
    data['category'] = to_s(attributes('td', 'category')[0], True)
    data['version'] = to_s(attributes('td', 'fixed-version')[0], True)
    data['description'] = to_text(issue('div', 'wiki')[0])
    data['history'] = to_text(html('div', id='history')[0])
    return data

def print_data(data):
    for item in sorted(data.keys()):
        print("{0:<12}: {1}".format(item, data[item]))

def main(argv=None):
    if argv is None:
        argv = sys.argv

    print_data(scrape(7399))

    return 0

if __name__ == '__main__':
    sys.exit(main())
