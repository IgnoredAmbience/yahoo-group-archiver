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
* Fetch all links
* Fetch all events in the calendar

Requirements:
* Python 2.7?
* Requests library

Usage:
```bash
pip install requests
./yahoo.py -u username groupname
```

If the 2FA is enabled on your account, you can extract the T and Y cookie from your browser and use the following:
```bash
./yahoo.py -ct 'YOUR_T_COOKIE' -cy 'YOUR_Y_COOKIE' groupname
```

Files will be placed into the directory structure groupname/{email,files,photos,databases,links,calendar}
