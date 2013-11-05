#!/usr/bin/env python
#
# redmine2bugzilla - export Redmine bugs to Bugzilla-importable XML

from __future__ import print_function
import sys, re
from datetime import datetime, timedelta
import urllib2, base64, textwrap
from xml.sax.saxutils import escape as xml_escape, quoteattr as xml_quoteattr
import argparse
from html2text import html2text
from BeautifulSoup import BeautifulSoup
from pytz import timezone
from tzlocal import get_localzone


redmine_base = 'http://redmine.example.com'

redmine_timezone = get_localzone()

searchable_id_formula = 'example-bug-{}'

bugzilla_default_user = 'bugs@example.com'
bugzilla_default_user_name = 'Maintainers'
bugzilla_users = {
    'John Doe': 'john.doe@example.com',
}

bugzilla_default_status = 'NEW'
bugzilla_statuses = {
    'need information': 'NEEDINFO',
    'review': 'ASSIGNED',
    'blocked': 'VERIFIED',
    'fixed': 'RESOLVED',
    'duplicate': 'RESOLVED',
    'invalid': 'RESOLVED',
}

bugzilla_default_resolution = ''
bugzilla_resolutions = {
    'fixed': 'FIXED',
    'duplicate': 'DUPLICATE',
    'invalid': 'INVALID',
}

# TODO: do these change with viewer/Redmine server prefs?
redmine_timestamp_pattern = r'\d\d/\d\d/\d\d\d\d \d\d:\d\d (?:a|p)m'
redmine_timestamp_re = re.compile(r'^{0}$'.format(redmine_timestamp_pattern))
redmine_timestamp_format = '%m/%d/%Y %I:%M %p'

redmine_href_ignore_re = re.compile(r'^(?!https?://)')

redmine_attachment_url_re = re.compile(r'^(/attachments)/(\d+/.*)$')
redmine_attachment_url_sub = r'\1/download/\2'
redmine_attachment_author_re = re.compile(r'^(.*?), ({0})$'.format(redmine_timestamp_pattern))

bugzilla_timestamp_format = '%Y-%m-%d %H:%M:%S %z'

debug = True


def debug_print(s):
    if debug:
        print(s, file=sys.stderr)

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
        for a in tag('a', href=redmine_href_ignore_re):
            a.replaceWith(a.string)
        for a in tag('a'):
            if a.has_key('href') and a['href'] == a.string:
                a.replaceWith(a.string)
        return html2text(unicode(tag)).strip()

    def to_date(s):
        return redmine_timezone.localize(datetime.strptime(s, redmine_timestamp_format))

    url = '{0}/issues/{1}'.format(redmine_base, bug_id)
    html = BeautifulSoup(urllib2.urlopen(url).read(), convertEntities=BeautifulSoup.HTML_ENTITIES)
    issue = html('div', 'issue')[0]
    author = issue('p', 'author')[0]
    times = author('a', title=redmine_timestamp_re)
    attributes = issue('table', 'attributes')[0]
    assignee = attributes('td', 'assigned-to')[0]
    attachments_divs = issue('div', 'attachments')
    attachments_div = attachments_divs[0] if attachments_divs else None
    histories = html('div', id='history')

    data = {}
    data['id'] = bug_id
    data['url'] = url
    data['project'] = to_s(html.h1, True)
    data['title'] = to_s(issue('div', 'subject')[0].h3)
    data['author'] = to_s(author.a)
    data['assignee'] = to_s(assignee.a if assignee.a is not None else assignee)
    data['created'] = to_date(times[0]['title'])
    data['updated'] = to_date(times[1]['title'])
    data['status'] = to_s(attributes('td', 'status')[0], True)
    data['priority'] = to_s(attributes('td', 'priority')[0], True)
    data['category'] = to_s(attributes('td', 'category')[0], True)
    data['version'] = to_s(attributes('td', 'fixed-version')[0], True) # FIXME: this is wrong
    data['description'] = to_text(issue('div', 'wiki')[0])
    data['history'] = to_text(histories[0]) if histories else None

    attachments = []
    for p in attachments_div('p') if attachments_div is not None else []:
        description = to_s(p.a.nextSibling)
        author_match = redmine_attachment_author_re.search(to_s(p('span', 'author')[0]))
        attachment_url = "{0}{1}".format(redmine_base,
                redmine_attachment_url_re.sub(redmine_attachment_url_sub, p.a['href']))
        handle = urllib2.urlopen(attachment_url)
        attachment_data = handle.read()

        attachment = {}
        attachment['url'] = attachment_url
        attachment['filename'] = to_s(p.a)
        attachment['type'] = handle.info().gettype()
        attachment['description'] = description.lstrip(' -').strip() if description is not None else None
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
                print_data(elem, "{0}[]/".format(item))
        else:
            datum = data[item]
            if item == 'data':
                datum = "{0}...".format(base64.b64encode(datum)[:48])
            print("{0}{1:<12}: {2}".format(pre, item, datum))

def xml_user(name):
    if name in bugzilla_users:
        return (bugzilla_users[name], name)
    return (bugzilla_default_user, bugzilla_default_user_name)

def E(x): return xml_escape(str(x) if x is not None else '')
def A(x): return xml_quoteattr(str(x) if x is not None else '')

def bug_xml_fields(data):
    author, author_name = xml_user(data['author'])
    assignee, assignee_name = xml_user(data['assignee'])
    no_author, no_author_name = xml_user(None)
    meta_time = data['created'] + timedelta(seconds=1)

    fields = {}
    def use(f): fields[f] = E(data[f])
    def use_date(f): fields[f] = E(data[f].strftime(bugzilla_timestamp_format))
    use('project')
    use('title')
    fields['author_name'] = A(author_name)
    fields['author'] = E(author)
    fields['assignee_name'] = A(assignee_name)
    fields['assignee'] = E(assignee)
    use_date('created')
    use_date('updated')
    fields['status'] = E(bugzilla_statuses.get(data['status'], bugzilla_default_status))
    fields['resolution'] = E(bugzilla_resolutions.get(data['status'], bugzilla_default_resolution))
    use('priority')
    use('category')
    use('version')
    use('description')
    fields['meta_author_name'] = A(no_author_name)
    fields['meta_author'] = E(no_author)
    fields['meta_updated'] = E(meta_time.strftime(bugzilla_timestamp_format))
    fields['meta'] = E("""
Original Redmine bug id: {id}
Original URL: {url}
Original author: {author}
Searchable id: {hash}
    """.format(
            id=data['id'],
            url=data['url'],
            author=data['author'],
            hash=searchable_id_formula.format(data['id'])
    ).strip())
    fields['historian_name'] = A(no_author_name)
    fields['historian'] = E(no_author)
    use('history')
    return fields

def attachment_xml_fields(attachment):
    author, _ = xml_user(attachment['author'])

    fields = {}
    def use(f): fields[f] = E(attachment[f])
    def use_date(f): fields[f] = E(attachment[f].strftime(bugzilla_timestamp_format))
    fields['is_patch'] = A(1 if attachment['type'] == 'text/x-patch' else 0)
    use('filename')
    use('type')
    use('description')
    fields['author'] = E(author)
    use_date('created')
    fields['data'] = E(textwrap.fill(base64.b64encode(attachment['data']), 76))
    return fields

def print_bug_xml(data, file=None):
    """Prints the results of scrape() as a snippet of Bugzilla XML"""

    if file is None:
        file = sys.stdout

    fields = bug_xml_fields(data)

    print("""
        <bug>
            <product>{project}</product>
            <short_desc>{title}</short_desc>
            <reporter name={author_name}>{author}</reporter>
            <assigned_to name={assignee_name}>{assignee}</assigned_to>
            <creation_ts>{created}</creation_ts>
            <delta_ts>{updated}</delta_ts>
            <bug_status>{status}</bug_status>
            <resolution>{resolution}</resolution>
            <priority>{priority}</priority>
            <component>{category}</component>
            <version>{version}</version>
            <long_desc>
                <who name={author_name}>{author}</who>
                <bug_when>{created}</bug_when>
                <thetext>{description}</thetext>
            </long_desc>
            <long_desc>
                <who name={meta_author_name}>{meta_author}</who>
                <bug_when>{meta_updated}</bug_when>
                <thetext>{meta}</thetext>
            </long_desc>""".format(**fields), file=file)

    if data['history'] is not None:
        print("""
            <long_desc>
                <who name={historian_name}>{historian}</who>
                <bug_when>{updated}</bug_when>
                <thetext>{history}</thetext>
            </long_desc>""".format(**fields), file=file)

    for attachment in data['attachments']:
        print("""
            <attachment ispatch={is_patch}>
                <filename>{filename}</filename>
                <type>{type}</type>
                <desc>{description}</desc>
                <attacher>{author}</attacher>
                <date>{created}</date>
                <data encoding="base64">{data}</data>
            </attachment>""".format(**attachment_xml_fields(attachment)), file=file)

    print("""
        </bug>""", file=file)

def redmine2bugzilla(bug_ids, file=None):
    """Exports the given bug ids as Bugzilla-importable XML to the given file or stdout"""

    if file is None:
        file = sys.stdout

    print("""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>""", file=file)
    print("<bugzilla>", file=file)

    for bug_id in bug_ids if type(bug_ids) is list else [bug_ids]:
        debug_print("Bug {0}...".format(bug_id))
        data = scrape(bug_id)
        print_bug_xml(data, file)

    print("</bugzilla>", file=file)

def main(argv=None):
    if argv is None:
        argv = sys.argv

    global redmine_base
    global redmine_timezone
    global searchable_id_formula
    global bugzilla_default_user
    global bugzilla_default_user_name
    global debug
    file = sys.stdout

    parser = argparse.ArgumentParser(prog=argv[0],
            description="export Redmine bugs to Bugzilla-importable XML")
    parser.add_argument('--redmine-base',
            help="Redmine base URL, default: {0}".format(redmine_base))
    parser.add_argument('--redmine-timezone',
            help="Redmine server timezone, default: {0}".format(redmine_timezone))
    parser.add_argument('--searchable-id-formula',
            help="pattern ({{}}=old bug id) used for a searchable hash, default: {0}".format(searchable_id_formula))
    parser.add_argument('--bugzilla-default-user',
            help="Bugzilla user when not in lookup table, default: {0}".format(bugzilla_default_user))
    parser.add_argument('--bugzilla-default-user-name',
            help="Bugzilla default user's real name, default: {0}".format(bugzilla_default_user_name))
    # TODO: specify other users, too.
    parser.add_argument('-s', '--scrape', metavar='BUG_ID', action='append',
            help="don't export; scrape and print data from the bug ids")
    parser.add_argument('-e', '--export', metavar='BUG_ID', action='append',
            help="export this bug id (if '-', read bug ids one per line from stdin)")
    parser.add_argument('-o', '--destination',
            help="export to this file (if '-', stdout), default: - (stdout)")
    parser.add_argument('-q', '--quiet', action='store_true', help="suppress normal debug output on stderr")
    args = parser.parse_args(argv[1:])

    if args.redmine_base is not None: redmine_base = args.redmine_base
    if args.redmine_timezone is not None: redmine_timezone = timezone(args.redmine_timezone)
    if args.searchable_id_formula is not None: searchable_id_formula = args.searchable_id_formula
    if args.bugzilla_default_user is not None: bugzilla_default_user = args.bugzilla_default_user
    if args.bugzilla_default_user_name is not None: bugzilla_default_user_name = args.bugzilla_default_user_name
    if args.destination is not None: file = open(args.destination, 'w') if args.destination != '-' else sys.stdout
    if args.quiet: debug = False

    if args.scrape is not None:
        for bug in args.scrape:
            print("Bug {0}".format(bug))
            print("----")
            print_data(scrape(bug))
            print("")
        return 0

    id_re = re.compile(r'^\d+$')

    exports = [e for e in args.export if id_re.match(e)]
    # TODO: don't wait for end of input to start the export process.
    if '-' in args.export:
        for line in sys.stdin:
            if id_re.match(line):
                exports.append(line.strip())

    # TODO: batch these in small groups, output to as many files as it takes.
    redmine2bugzilla(exports, file)
    return 0

if __name__ == '__main__':
    sys.exit(main())
