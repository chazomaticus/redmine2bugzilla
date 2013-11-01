#!/usr/bin/env python
#
# redmine2bugzilla - export Redmine bugs to Bugzilla-importable XML

import sys
import time
import re
import urllib2
import argparse
from BeautifulSoup import BeautifulSoup
from html2text import html2text

redmine_base = 'http://redmine.example.com'

# TODO: do these change with viewer/server prefs?
timestamp_pattern = r'\d\d/\d\d/\d\d\d\d \d\d:\d\d (?:a|p)m'
timestamp_re = re.compile('^{0}$'.format(timestamp_pattern))
timestamp_format = '%m/%d/%Y %I:%M %p'

href_ignore_re = re.compile(r'^(?!https?://)')

attachment_url_re = re.compile(r'^(/attachments)/(\d+/.*)$')
attachment_url_sub = r'\1/download/\2'
attachment_author_re = re.compile(r'^(.*?), ({0})$'.format(timestamp_pattern))

def scrape(bug_id):
    """Returns a dictionary of information about a Redmine bug"""

    def to_s(tag, lower=False):
        s = unicode(tag.string)
        if s == '-' or s.strip() == '':
            return None
        if lower:
            return s.lower()
        return s

    def to_text(tag):
        for img in tag('img'):
            img.extract()
        for a in tag('a', href=href_ignore_re):
            a.replaceWith(a.string)
        return html2text(unicode(tag)).strip()

    url = '{0}/issues/{1}'.format(redmine_base, bug_id)
    html = BeautifulSoup(urllib2.urlopen(url).read(), convertEntities=BeautifulSoup.HTML_ENTITIES)
    issue = html('div', 'issue')[0]
    author = issue('p', 'author')[0]
    times = author('a', title=timestamp_re)
    attributes = issue('table', 'attributes')[0]
    assignee = attributes('td', 'assigned-to')[0]
    attachments_divs = issue('div', 'attachments')
    attachments_div = attachments_divs[0] if attachments_divs else None

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

    attachments = []
    for p in attachments_div('p') if attachments_div != None else []:
        description = to_s(p.a.nextSibling)
        author_match = attachment_author_re.search(to_s(p('span', 'author')[0]))

        attachment = {}
        attachment['filename'] = to_s(p.a)
        attachment['description'] = description.lstrip(' -').strip() if description != None else None
        attachment['author'] = author_match.group(1)
        attachment['created'] = time.strptime(author_match.group(2), timestamp_format)
        attachment['url'] = "{0}{1}".format(redmine_base, attachment_url_re.sub(attachment_url_sub, p.a['href']))
        attachments.append(attachment)

    data['attachments'] = attachments
    return data

def print_data(data, pre=''):
    """Prints the results of scrape() in a relatively sane format"""

    for item in sorted(data.keys()):
        if type(data[item]) is list: # Assume list of dicts
            for elem in data[item]:
                print_data(elem, "{0}[]/".format(item))
        else:
            print("{0}{1:<12}: {2}".format(pre, item, data[item]))

def main(argv=None):
    if argv is None:
        argv = sys.argv

    global redmine_base

    parser = argparse.ArgumentParser(prog=argv[0],
            description="export Redmine bugs to Bugzilla-importable XML")
    parser.add_argument('-r', '--redmine-base',
            help="redmine base URL, default: {0}".format(redmine_base))
    parser.add_argument('-s', '--scrape', metavar='BUG_ID', action='append', default=[],
            help="scrape and print data from the bug id")
    args = parser.parse_args(argv[1:])

    if args.redmine_base != None:
        redmine_base = args.redmine_base

    for bug in args.scrape:
        print("Bug {0}".format(bug))
        print("----")
        print_data(scrape(bug))
        print("")

    return 0

if __name__ == '__main__':
    sys.exit(main())
