yahoo-group-archiver  
pipeline mode
====================

* Python 3.5 - 3.8  

git clone https://github.com/ArchiveTeam/yahoo-group-archiver.git  
cd yahoo-group-archiver  
Usage:
```bash
pip3 install -r requirements.txt
run-pipeline3 ./pipeline.py $USERNAME
```
Watch:  
http://tracker-test.ddns.net/yahoo-groups-api/

---

yahoo-group-archiver  
manual mode
====================

* Python 3.5 - 3.8  

git clone https://github.com/ArchiveTeam/yahoo-group-archiver.git  
cd yahoo-group-archiver  

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
2. Click the 🔒 padlock, or ⓘ (cicled letter i) in the address bar to the left of the website address.
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

## Command Line Options
```
usage: yahoo.py [-h] [-ct COOKIE_T] [-cy COOKIE_Y] [-ce COOKIE_E]
                [-cf COOKIE_FILE] [-e] [-at] [-f] [-i] [-t] [-tr] [-d] [-l]
                [-c] [-p] [-a] [-m] [-o] [--user-agent USER_AGENT]
                [--start START] [--stop STOP] [--ids IDS [IDS ...]] [-w] [-v]
                [--colour] [--delay DELAY]
                group

positional arguments:
  group

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose
  --colour, --color     Colour log output to terminal
  --delay DELAY         Minimum delay between requests (default 0.2s)

Authentication Options:
  -ct COOKIE_T, --cookie_t COOKIE_T
                        T authentication cookie from yahoo.com
  -cy COOKIE_Y, --cookie_y COOKIE_Y
                        Y authentication cookie from yahoo.com
  -ce COOKIE_E, --cookie_e COOKIE_E
                        Additional EuConsent cookie is required in EU
  -cf COOKIE_FILE, --cookie-file COOKIE_FILE
                        File to store authentication cookies to. Cookies
                        passed on the command line will overwrite any already
                        in the file.

What to archive:
  By default, all the below.

  -e, --email           Only archive email and attachments (from email)
  -at, --attachments    Only archive attachments (from attachments list)
  -f, --files           Only archive files
  -i, --photos          Only archive photo galleries
  -t, --topics          Only archive HTML email and attachments through the
                        topics API
  -tr, --topicsWithRaw  Only archive both HTML and raw email and attachments
                        through the topics API
  -d, --database        Only archive database
  -l, --links           Only archive links
  -c, --calendar        Only archive events
  -p, --polls           Only archive polls
  -a, --about           Only archive general info about the group
  -m, --members         Only archive members
  -o, --overwrite       Overwrite existing files such as email and database
                        records

Request Options:
  --user-agent USER_AGENT
                        Override the default user agent used to make requests

Message Range Options:
  Options to specify which messages to download. Use of multiple options
  will be combined. Note: These options will also try to fetch message IDs
  that may not exist in the group.

  --start START         Email message id to start from (specifying this will
                        cause only specified message contents to be
                        downloaded, and not message indexes). Default to 1, if
                        end option provided.
  --stop STOP           Email message id to stop at (inclusive), defaults to
                        last message ID available, if start option provided.
  --ids IDS [IDS ...]   Get email message by ID(s). Space separated,
                        terminated by another flag or --

Output Options:
  -w, --warc            Output WARC file of raw network requests. [Requires
                        warcio package installed]
