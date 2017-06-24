Twitter Collector
=================

A system to collect tweets and information regarding the tweets, including trending hashtags and users.

Targets
-------

- To find the current trending hashtags and tweets of these tags
- To collect tweets from the timeline of target user(s)
- To search and generate charts from the trending data
- To report the charts to specified email at defined time

Requirements
------------

- Twitter account
- Twitter API keys
- PostgreSQL
- Python 3 environment and packages below:
	- pandas
	To use DataFrame for plot data
	- psycopg2
	To connect with postgreSQL
	- requests
	To make requests to twitter
	- langdetect
	To ignore data from few languages not of my interest (These include language codes: ar, fa, ka)
	- matplotlib
	To plot data
	- requests_oauthlib
	OAuth is required by twitter API

How to use
----------
1. Clone all files into a single directory
2. Modify files in the directory `Settings`
	- Keys (Required)
	Twitter API keys
	- Email (Optional)
	Pass on if you `do not require` email report
	`fromAddress` is the `sender` (your gmail) and `toAddress` is the `recipient`, and the `sender's password`
	`reportHours` is the `target hours` the system providing report
	- psql (Optional)
	If you intent to change any of these, you will need to consider to modify the postgreSQL script provided
	- accounts (Optional)
	The twitter user accounts to check
3. Go to your PostgreSQL's psql and execute the script `db-Script`. This will generate the user account, database, tables and auto-vacuum. Scripts in `For-Tables-Script` are some scripts that might be handy including create index.

License
-------

Under MIT License.