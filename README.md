yahoo-group-archiver
====================

**Note:** Yahoo now have a ["Get My Data" tool](https://groups.yahoo.com/neo/getmydata)
available, which may provide an alternative to this tool, although the content it provides is not
known at the time of writing.

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
* Python 2.7

Usage:
```bash
pip install -r requirements.txt
./yahoo.py -ct "<T_cookie>" -cy "<Y_cookie>" "<groupid>"
```

You will need to get the `T` and `Y` cookie values from an authenticated
browser session.
In Google Chrome these steps are required:
1. Go to [Yahoo Groups](https://groups.yahoo.com/neo).
2. Click the ⓘ (cicled letter i) in the address bar.
3. Click "Cookies".
4. On the Allowed tab select "Yahoo.com" followed by "Cookies" in the tree listing.
5. Select the T cookie and copy the Content field in place of `<T_cookie>` in the above command line.
6. Select the Y cookie and copy the Content field in place of `<Y_cookie>` in the above command line.

Note: the string you paste _must_ be surrounded by quotes.

Using the `--cookie-file` (or `-cf`) option allows you to specify a file in which the authentication cookies will be
loaded and saved in.

Files will be placed into the directory structure groupname/{email,files,photos,databases}
