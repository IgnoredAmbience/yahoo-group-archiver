yahoo-group-archiver
====================

Archives a Yahoo group using the non-public API

Features
* Saves full email content
* Fetches email attachments and recombines with email
* Downloads attachments as separate files
* Fetch all files
* Fetch all photos
* Fetch all database tables

Requirements:
* Python 2.7?
* Requests library

Usage:
```bash
pip install requests
./yahoo.py -u username -ct <T_cookie> -cy <Y_cookie> groupname
```

You will need to get the `T` and `Y` cookie values from an authenticated
browser session.

Files will be placed into the directory structure groupname/{email,files,photos,databases}
