yahoo-group-archiver
====================

This tool archives a Yahoo group using the non-public API used by the Yahoo Groups website UI.

Features:
* Saves full email content
* Downloads attachments as separate files
* Fetch all files
* Fetch all photos
* Fetch all database tables
* Fetch all links
* Fetch all events in the calendar
* Fetch all polls

Requirements:
* Python 2.7 or 3+

Usage:
```bash
pip install -r requirements.txt
./yahoo.py -ct '<T_cookie>' -cy '<Y_cookie>' '<groupid>'
```

You will need to get the `T` and `Y` cookie values from an authenticated
browser session.

The cookies should look like this, where `someLongText` and `someShortText` are arbitrary strings:
- T: `z=someLongText&a=someLongText&sk=someLongText&ks=someLongText&kt=someLongText&ku=someLongText&d=someLongText&af=someLongText`
- Y: `v=1&n=someLongText&l=someShortText=someShortText&r=hp&intl=us`

In Google Chrome these steps are required:
1. Go to [Yahoo Groups](https://groups.yahoo.com/neo).
2. Click the ⓘ (cicled letter i) in the address bar.
3. Click "Cookies".
4. On the Allowed tab select "Yahoo.com" followed by "Cookies" in the tree listing.
5. Select the T cookie and copy the Content field in place of `<T_cookie>` in the above command line.
6. Select the Y cookie and copy the Content field in place of `<Y_cookie>` in the above command line.

In Firefox:
1. Go to [Yahoo Groups](https://groups.yahoo.com/neo) (make sure you're signed in with your account).
2. Press Shift-F9 or select the menu Tools/Web Developer/Storage Inspector.
3. Double click on the T cookie's value and copy the content in place of `<T_cookie>` in the above command line.
4. Double click on the Y cookie's value and copy the content in place of `<Y_cookie>` in the above command line.

Note: the string you paste _must_ be surrounded by quotes.

Using the `--cookie-file` (or `-cf`) option allows you to specify a file in which the authentication cookies will be
loaded and saved in.

Files will be placed into the directory structure groupname/{email,files,photos,databases}

## Alternatives to this tool
### Yahoo Get My Data
Yahoo have a ["Get My Data" tool](https://groups.yahoo.com/neo/getmydata) for downloading content of groups of which you
are a member.
It gives you:
* all group emails in .mbox format, _with all addresses unredacted_
* all files (except attachments)
* all links
* photos and attachments _you_ sent/uploaded to the group
No further data is returned, even if you are group owner.

The primary benefit to using the Yahoo tool is for retrieving the full, unredacted email archive for a group. Archival
methods that scrape the API from a non-moderator/owner(?) account will have email addresses in the message contents
redacted.

Downsides to using this tool are that not all group content is returned, even for group owners!
The current lag time from requesting the data to being able to download it is about a week at the time of writing.

One user of Yahoo's Get My Data described it as ["woefully
incomplete"](https://github.com/IgnoredAmbience/yahoo-group-archiver/issues/87).
