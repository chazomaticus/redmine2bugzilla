#!/usr/bin/env python
#
# redmine2bugzilla - export Redmine bugs to Bugzilla-importable XML
# Copyright (C) 2013 Yorba Foundation
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import sys, os, re, codecs
from datetime import datetime, timedelta
import urllib2, base64, textwrap
from xml.sax.saxutils import escape as xml_escape, quoteattr as xml_quoteattr
import argparse
# TODO: import these under try:, provide a helpful error.
from BeautifulSoup import BeautifulSoup
from html2text import html2text
from pytz import timezone
from tzlocal import get_localzone


class Config:
    def __init__(self):
        # In approximate decreasing order of your likelihood to want to edit:

        self.exporter = os.getenv('EMAIL', 'you@example.com')
        self.redmine_base = 'http://redmine.example.com'

        self.searchable_id_formula = 'example-bug-{0}'

        self.bugzilla_default_user = 'bugs@example.com'
        self.bugzilla_default_user_name = 'Maintainers'
        self.bugzilla_users = {
            # 'Redmine Name': 'bugzilla-account-name',
            # e.g.: 'John Doe': 'john.doe@example.com',
        }

        self.bugzilla_maintainer = 'bugzilla@example.com'
        self.bugzilla_version = '3.4.13'

        self.redmine_timezone = get_localzone()

        self.bugzilla_default_status = 'NEW'
        self.bugzilla_statuses = {
            'need information': 'NEEDINFO',
            'review': 'ASSIGNED',
            'blocked': 'VERIFIED',
            'fixed': 'RESOLVED',
            'duplicate': 'RESOLVED',
            'invalid': 'RESOLVED',
        }

        self.bugzilla_default_resolution = None
        self.bugzilla_resolutions = {
            'fixed': 'FIXED',
            'duplicate': 'DUPLICATE',
            'invalid': 'INVALID',
        }

        # TODO: do these change with viewer/Redmine server prefs?
        self.redmine_timestamp_pattern = r'\d\d/\d\d/\d\d\d\d \d\d:\d\d (?:a|p)m'
        self.redmine_timestamp_re = re.compile(r'^{0}$'.format(self.redmine_timestamp_pattern))
        self.redmine_timestamp_format = '%m/%d/%Y %I:%M %p'

        self.redmine_issue_class_re = re.compile(r'^issue\b')
        self.redmine_href_ignore_re = re.compile(r'^(?!https?://)')

        self.redmine_attachment_url_re = re.compile(r'^(/attachments)/((\d+)/.*)$')
        self.redmine_attachment_url_sub = r'\1/download/\2'
        self.redmine_attachment_id_sub = r'\3'
        self.redmine_attachment_author_re = re.compile(r'^(.*?), ({0})$'.format(self.redmine_timestamp_pattern))

        self.bugzilla_timestamp_format = '%Y-%m-%d %H:%M:%S %z'

        self.debug = True

        self.file = codecs.getwriter('UTF-8')(sys.stdout)


def debug_print(s, config):
    if config.debug:
        print(s, file=sys.stderr)

def scrape(bug_id, config):
    """Returns a dictionary of information about a Redmine bug"""

    def first(tags):
        return tags[0] if tags and len(tags) > 0 else None

    def to_s(tag, lower=False):
        s = unicode(BeautifulSoup(tag.string, convertEntities=BeautifulSoup.HTML_ENTITIES).contents[0])
        if s == '-' or s.strip() == '':
            return None
        if lower:
            return s.lower()
        return s

    def to_text(tag):
        if not tag:
            return None
        for img in tag('img'):
            img.extract()
        for a in tag('a', href=config.redmine_href_ignore_re):
            a.replaceWith(a.string)
        for a in tag('a'):
            if a.has_key('href') and a['href'] == a.string:
                a.replaceWith(a.string)
        return html2text(unicode(tag)).strip()

    def to_date(s):
        return config.redmine_timezone.localize(datetime.strptime(s, config.redmine_timestamp_format))

    url = '{0}/issues/{1}'.format(config.redmine_base, bug_id)
    debug_print(u"Scraping {0}...".format(url), config)

    html = BeautifulSoup(urllib2.urlopen(url).read())
    issue = first(html('div', attrs={'class': config.redmine_issue_class_re})) # Odd syntax necessary for old BS3
    author = first(issue('p', 'author'))
    times = author('a', title=config.redmine_timestamp_re)
    attributes = first(issue('table', 'attributes'))
    assignee = first(attributes('td', 'assigned-to'))
    version = first(attributes('td', 'fixed-version'))
    attachments_div = first(issue('div', 'attachments'))

    data = {}
    data['id'] = bug_id
    data['url'] = url
    data['project'] = to_s(html.h1, True)
    data['title'] = to_s(first(issue('div', 'subject')).h3)
    data['author'] = to_s(author.a)
    data['assignee'] = to_s(assignee.a if assignee.a else assignee)
    data['created'] = to_date(times[0]['title'])
    data['updated'] = to_date(times[1]['title']) if len(times) > 1 else None
    data['status'] = to_s(first(attributes('td', 'status')), True)
    data['priority'] = to_s(first(attributes('td', 'priority')), True)
    data['category'] = to_s(first(attributes('td', 'category')), True)
    data['version'] = to_s(version.a if version.a else version, True)
    data['description'] = to_text(first(issue('div', 'wiki')))
    data['history'] = to_text(first(html('div', id='history')))

    attachments = []
    for p in attachments_div('p') if attachments_div else []:
        link = p.a['href']
        description = to_s(p.a.nextSibling)
        author_match = config.redmine_attachment_author_re.search(to_s(p('span', 'author')[0]))
        attachment_url = '{0}{1}'.format(config.redmine_base,
                config.redmine_attachment_url_re.sub(config.redmine_attachment_url_sub, link))
        handle = urllib2.urlopen(attachment_url)
        attachment_data = handle.read()

        attachment = {}
        attachment['id'] = config.redmine_attachment_url_re.sub(config.redmine_attachment_id_sub, link)
        attachment['url'] = attachment_url
        attachment['filename'] = to_s(p.a)
        attachment['type'] = handle.info().gettype()
        attachment['description'] = description.lstrip(' -').strip() if description else None
        attachment['author'] = author_match.group(1)
        attachment['created'] = to_date(author_match.group(2))
        attachment['data'] = attachment_data
        attachments.append(attachment)

    data['attachments'] = attachments
    return data

def print_data(data, pre=''):
    """Prints the results of scrape() in a debug format"""

    for item in sorted(data.keys()):
        if type(data[item]) is list: # Assume list of dicts
            for elem in data[item]:
                print_data(elem, u"{0}[]/".format(item))
        else:
            datum = data[item]
            if item == 'data':
                datum = u"{0}...".format(base64.b64encode(datum)[:48])
            print(u"{0}{1:<12}: {2}".format(pre, item, datum))

def xml_user(name, config):
    if name in config.bugzilla_users:
        return (config.bugzilla_users[name], name)
    return (config.bugzilla_default_user, config.bugzilla_default_user_name)

def E(x): return xml_escape(unicode(x) if x else '')
def A(x): return xml_quoteattr(unicode(x) if x else '')

def bug_xml_fields(data, config):
    author, author_name = xml_user(data['author'], config)
    assignee, assignee_name = xml_user(data['assignee'], config)
    no_author, no_author_name = xml_user(None, config)

    fields = {}
    def use(f): fields[f] = E(data[f])
    use('id')
    use('project')
    use('title')
    fields['author_name'] = A(author_name)
    fields['author'] = E(author)
    fields['assignee_name'] = A(assignee_name)
    fields['assignee'] = E(assignee)
    fields['created'] = E(data['created'].strftime(config.bugzilla_timestamp_format))
    fields['updated'] = E(data['updated'].strftime(config.bugzilla_timestamp_format) if data['updated'] else None)
    fields['status'] = E(config.bugzilla_statuses.get(data['status'], config.bugzilla_default_status))
    fields['resolution'] = E(config.bugzilla_resolutions.get(data['status'], config.bugzilla_default_resolution))
    use('priority')
    use('category')
    use('version')
    fields['description'] = E(u"""
Original Redmine bug id: {id}
Original URL: {url}
Searchable id: {hash}
Original author: {author}
Original description:

{description}
    """.format(
            id=data['id'],
            url=data['url'],
            hash=config.searchable_id_formula.format(data['id']),
            author=data['author'],
            description=data['description']
    ).strip())
    fields['historian_name'] = A(no_author_name)
    fields['historian'] = E(no_author)
    use('history')
    return fields

def attachment_xml_fields(attachment, config):
    author, _ = xml_user(attachment['author'], config)

    fields = {}
    def use(f): fields[f] = E(attachment[f])
    use('id')
    fields['is_patch'] = A('1' if attachment['type'] == 'text/x-patch' else '0')
    use('filename')
    use('type')
    fields['description'] = E(attachment['description'] if attachment['description'] else attachment['filename'])
    fields['author'] = E(author)
    fields['created'] = E(attachment['created'].strftime(config.bugzilla_timestamp_format))
    fields['data'] = E(textwrap.fill(base64.b64encode(attachment['data']), 76))
    return fields

def print_bug_xml(data, config):
    """Prints the results of scrape() as a snippet of Bugzilla XML"""

    fields = bug_xml_fields(data, config)

    print(u"""
        <bug>
            <bug_id>{id}</bug_id>
            <product>{project}</product>
            <short_desc>{title}</short_desc>
            <reporter name={author_name}>{author}</reporter>
            <assigned_to name={assignee_name}>{assignee}</assigned_to>
            <creation_ts>{created}</creation_ts>
            <delta_ts>{updated}</delta_ts>
            <bug_status>{status}</bug_status>
            <resolution>{resolution}</resolution>
            <priority>{priority}</priority>
            <bug_severity>normal</bug_severity>
            <component>{category}</component>
            <version>{version}</version>
            <rep_platform>All</rep_platform>
            <op_sys>All</op_sys>
            <actual_time>0</actual_time>
            <long_desc>
                <who name={author_name}>{author}</who>
                <bug_when>{created}</bug_when>
                <thetext>{description}</thetext>
            </long_desc>""".format(**fields), file=config.file)

    if data['history']:
        print(u"""
            <long_desc>
                <who name={historian_name}>{historian}</who>
                <bug_when>{updated}</bug_when>
                <thetext>{history}</thetext>
            </long_desc>""".format(**fields), file=config.file)

    for attachment in data['attachments']:
        print(u"""
            <attachment ispatch={is_patch}>
                <attachid>{id}</attachid>
                <filename>{filename}</filename>
                <type>{type}</type>
                <desc>{description}</desc>
                <attacher>{author}</attacher>
                <date>{created}</date>
                <data encoding="base64">{data}</data>
            </attachment>""".format(**attachment_xml_fields(attachment, config)), file=config.file)

    print(u"""
        </bug>""", file=config.file)

def header_xml_fields(config):
    fields = {}
    fields['version'] = A(config.bugzilla_version)
    fields['base'] = A('{0}/'.format(config.redmine_base))
    fields['exporter'] = A(config.exporter)
    fields['maintainer'] = A(config.bugzilla_maintainer)
    return fields

def redmine2bugzilla(bug_ids, config=None):
    """Exports the given bug ids as Bugzilla-importable XML"""

    if config is None:
        config = Config()

    print(u"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<!DOCTYPE bugzilla SYSTEM "https://bugzilla.mozilla.org/page.cgi?id=bugzilla.dtd">
<bugzilla
    version={version}
    urlbase={base}
    exporter={exporter}
    maintainer={maintainer}
>
    """.format(**header_xml_fields(config)), file=config.file)

    for bug_id in bug_ids if type(bug_ids) is list else [bug_ids]:
        data = scrape(bug_id, config)
        print_bug_xml(data, config)

    print(u"</bugzilla>", file=config.file)

def main(argv=None):
    if argv is None:
        argv = sys.argv

    config = Config()

    parser = argparse.ArgumentParser(prog=argv[0],
            description=u"export Redmine bugs to Bugzilla-importable XML")
    parser.add_argument('-e', '--export', metavar='BUG_ID', action='append',
            help=u"export this bug id (if '-', read bug ids one per line from stdin)")
    parser.add_argument('-o', '--destination',
            help=u"export to this file (if '-', stdout), default: - (stdout)")
    parser.add_argument('-s', '--scrape', metavar='BUG_ID', action='append',
            help=u"don't export; scrape and print data from the bug ids on stdout")
    parser.add_argument('--exporter',
            help=u"Your email address, default: {0}".format(config.exporter))
    parser.add_argument('--redmine-base',
            help=u"Redmine base URL (no trailing slash), default: {0}".format(config.redmine_base))
    parser.add_argument('--searchable-id-formula',
            help=u"pattern ({{0}}=old bug id) used for a searchable hash, default: {0}".format(config.searchable_id_formula))
    parser.add_argument('--bugzilla-default-user',
            help=u"Bugzilla user when not in lookup table, default: {0}".format(config.bugzilla_default_user))
    parser.add_argument('--bugzilla-default-user-name',
            help=u"Bugzilla default user's real name, default: {0}".format(config.bugzilla_default_user_name))
    # TODO: specify other users, too.
    parser.add_argument('--bugzilla-maintainer',
            help=u"Bugzilla maintainer email, default: {0}".format(config.bugzilla_maintainer))
    parser.add_argument('--bugzilla-version',
            help=u"Bugzilla version number, default: {0}".format(config.bugzilla_version))
    parser.add_argument('--redmine-timezone',
            help=u"Redmine server timezone, default: {0}".format(config.redmine_timezone))
    parser.add_argument('-q', '--quiet', action='store_true', help=u"suppress normal debug output on stderr")
    args = parser.parse_args(argv[1:])

    if args.destination and args.destination != '-':
        config.file = codecs.open(args.destination, 'w', encoding='UTF-8') # TODO: close this.
    if args.exporter: config.exporter = args.exporter
    if args.redmine_base: config.redmine_base = args.redmine_base
    if args.searchable_id_formula: config.searchable_id_formula = args.searchable_id_formula
    if args.bugzilla_default_user: config.bugzilla_default_user = args.bugzilla_default_user
    if args.bugzilla_default_user_name: config.bugzilla_default_user_name = args.bugzilla_default_user_name
    if args.bugzilla_maintainer: config.bugzilla_maintainer = args.bugzilla_maintainer
    if args.bugzilla_version: config.bugzilla_version = args.bugzilla_version
    if args.redmine_timezone: config.redmine_timezone = timezone(args.redmine_timezone)
    if args.quiet: config.debug = False

    if args.scrape:
        for bug in args.scrape:
            print(u"Bug {0}".format(bug))
            print(u"----")
            print_data(scrape(bug, config))
            print(u"")
        return 0

    id_re = re.compile(r'^\d+$')

    args_export = args.export or []
    exports = [e for e in args_export if id_re.match(e)]
    # TODO: don't wait for end of input to start the export process.
    if '-' in args_export:
        for line in sys.stdin:
            if id_re.match(line):
                exports.append(line.strip())

    if not exports:
        debug_print(u"Nothing to export; run with --help for help", config)
        return 0

    # TODO: batch these in small groups, output to as many files as it takes.
    redmine2bugzilla(exports, config)
    return 0

if __name__ == '__main__':
    sys.exit(main())
