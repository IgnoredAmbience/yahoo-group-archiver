yahoo-group-archiver
====================

Archives a Yahoo group using the non-public API

Features
* Saves full email content
* Downloads attachments as separate files
* Fetch all files
* Fetch all photos
* Fetch all database tables
* Fetch all links
* Fetch all events in the calendar
* Fetch all polls

Requirements:
* Python 2.7?
* Requests library

Usage:
```bash
pip install requests
./yahoo.py -ct 'YOUR_T_COOKIE' -cy 'YOUR_Y_COOKIE' groupname
```

You can extract the T and Y cookie from your browser.


Files will be placed into the directory structure groupname/{email,files,photos,databases,links,calendar,polls}
