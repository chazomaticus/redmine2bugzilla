redmine2bugzilla
================

redmine2bugzilla is a simple script to export Redmine bugs to an XML format
compatible with Bugzilla's [importxml.pl][0] script.  It works by scraping
public Redmine HTML for data, and converting that into a format readable by
Bugzilla.  It was tested extensively by exporting bugs from a Redmine 1.3.3
install into [GNOME's Bugzilla][https://bugzilla.gnome.org/], running version
3.4.13.  I can't vouch for any other combination of installations.

Dependencies
------------

* [Beautiful Soup](http://www.crummy.com/software/BeautifulSoup/)
* [html2text](https://pypi.python.org/pypi/html2text)
* [pytz](https://pypi.python.org/pypi/pytz)
* [tzlocal](https://pypi.python.org/pypi/tzlocal)

In Ubuntu, these commands will give you the right packages:

    $ sudo apt-get install python-beautifulsoup python-pip
    $ sudo pip install html2text pytz tzlocal

Usage
-----

To see the scraping in action, run something like

    $ ./redmine2bugzilla.py --redmine-base http://redmine.example.com -s 1234

This will scrape bug `1234` in the `redmine.example.com` Redmine instance and
print out the bug's data.  You can use this to eyeball the script and make sure
it's finding the correct fields.

To export Redmine bugs to Bugzilla-importable XML, use `-e`:

    $ ./redmine2bugzilla.py --redmine-base http://redmine.example.com \
      --bugzilla-default-user bugs@example.com \
      --bugzilla-maintainer admin@example.com -e 1234 > bugs.xml

This will scrape the same bug, but this time write importable XML to
`bugs.xml`.

See `./redmine2bugzilla.py --help` for full usage information.

To import into Bugzilla, transfer the export XML file to the Bugzilla server,
then run something like:

    $ ./importxml.pl -v bugs.xml

See the [importxml.pl docs][0] for more information.

Note that before you do the import, you'll want to set up all Bugzilla
products, components, and versions to match exactly the Redmine projects,
categories, and target versions, respectively.

I also highly recommend running an import in a testing environment before
jumping in with production data.  Bugzilla will tell you what went wrong for
each bug, and this way you'll have a chance to fix it before any damage is
done.

Notes
-----

You may find it easier to simply edit the default config information at the top
of the script than having to specify a bunch of long command line arguments.
There are some things that I didn't bother making command line arguments for,
like adding extra Bugzilla users, and editing the file is the only way to
change.

Because this works by scraping the HTML, it only works for public bugs.  It
shouldn't be too hard to extend this with the proper cookie code to allow it to
scrape bugs viewable only when logged in, but I didn't need that feature.

Because this pulls down the data for all attachments, you may want to run this
on the server or somewhere close to it, where bandwidth won't be a concern.

There are a couple benefits to scraping the HTML over using the Redmine Ruby
API:
* It gives you a little more flexibility in where you run it, so you could
  scrape bugs you may not have server access to.
* We pull the whole bug history div as one Bugzilla "comment", which is a nice
  compromise between readability and preservation of information.
* I found html2text more reliable than any textile to markdown converter I
  could find, especially because scraping makes it easy to control what data is
  being converted.

XML Format
----------

Here's what I learned about the XML format Bugzilla expects in its
`importxml.pl` script.  I could find no documentation about this format beyond
"it's like when you click the XML link at the bottom of a bug listing".  Many
of the tags are obvious, but some aren't.

`bugzilla` tag attributes:
* `version` gets checked against the version of the destination Bugzilla
  database.
* `urlbase` should be set to the base URL of the bug database being exported.
  It gets concatenated with `show_bug.cgi?id=` and the bug's `bug_id` tag in
  some text describing where the bug came from.
* `maintainer` and `exporter` should be set to the email addresses for the
  maintainer of the bug database being exported and your email address,
  respectively.  `importxml.pl` can send these addresses a summary of the
  import process.  It won't import without these attributes set.

`bug` tag children:
* `bug_id` should be set to the id of the bug being exported, whatever it is.
  Bugzilla uses this to make up a URL for the original bug.  It'll be wrong for
  Redmine.  Oh well.  (It looks like in more modern versions of Bugzilla, the
  `importxml.pl` script accepts a `--bug_page` argument that can fix this.)
* Attachments need to have a non-empty `attachid` tag.  It seems to be ignored,
  and can be `x`.  It just won't import the attachment without it set.
* The `encoding` attribute on attachments' `data` tag can have the value
  `filename`, in which case `importxml.pl` will open the specified file.  This
  requires the `--attach_path` argument.  This script instead includes
  attachments inline, base64-encoded.

Everything else seemed fairly straightforward to me.

Good luck!


[0]: http://www.bugzilla.org/docs/tip/en/html/api/importxml.html
