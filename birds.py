#===============================================================================================================================================
import os
import sys
import json
import time
import smtplib
import psycopg2
import datetime
import requests
import threading
import langdetect
import matplotlib
matplotlib.use('Agg')
import pandas as pd
import matplotlib.pyplot as plt
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from requests_oauthlib import OAuth1, OAuth1Session

# sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)

#===============================================================================================================================================
class tweetCollect(object):
#===============================================================================================================================================
	def __init__(self):
		self.user_timeline_url = 'https://api.twitter.com/1.1/statuses/user_timeline.json'
		self.tweet_search_url = 'https://api.twitter.com/1.1/search/tweets.json'
		self.trends_place_url = 'https://api.twitter.com/1.1/trends/place.json'
		self.available_url = 'https://api.twitter.com/1.1/trends/available.json'

		self.fromAddr = ''
		self.toAddr = ''
		self.emailPass = ''
		self.targetTime = []
		self.keys = []
		self.twitterAccounts = []
		self.dbInfo = {}
		self.keyFields = ["Consumer Key (API Key)", "Consumer Secret (API Secret)", "Access Token", "Access Token Secret"]
		self.rate_limits = {
								'search_tweets' : { 'limit' : 0, 'remain' : 0 },
								'user_timeline' : { 'limit' : 0, 'remain' : 0 },
								'trends_place' : { 'limit' : 0, 'remain' : 0 },
							}

		self.nowTime = 0
		self.resetTime = 0
		self.includeAFK = False

		self.getKeys()
		self.getDBInfo()
		self.checkRates()

		try:
			self.conn = psycopg2.connect(database=self.dbInfo['database'], user=self.dbInfo['user'], password=self.dbInfo['password'], host=self.dbInfo['host'], port=self.dbInfo['port'])
			self.cur = self.conn.cursor()
			self.tCur = self.conn.cursor()
			self.uCur = self.conn.cursor()

			self.getLocations()
			self.checkRates()

			print('[Starting Time  : %s]' % self.obtainDT())
			print('[Next Reset Time: %s]' % self.resetTime)

			theratesThread = threading.Thread(target=self.getRates, args=(60,))
			trendingThread = threading.Thread(target=self.getTrending, args=(300,1))
			timelineThread = threading.Thread(target=self.getTimeline, args=(900,))
			tSummaryThread = threading.Thread(target=self.getTrendSummary, args=(3600,))
			
			try:
				theratesThread.start()
				trendingThread.start()
				timelineThread.start()
				tSummaryThread.start()
			except:
				cur.close()
				tCur.close()
				uCur.close()
				conn.close()
		except:
			print('Failed to connect to server!')

#===============================================================================================================================================
	def getDBsize(self):
		sizeCur = self.conn.cursor()
		sizeCur.execute("select pg_size_pretty(pg_database_size(%s))", ('twitter',))
		print(sizeCur.fetchone()[0])

#===============================================================================================================================================
	def obtainTime(self):
		self.nowTime = datetime.datetime.now().strftime('%H:%M:%S')
		return self.nowTime

#===============================================================================================================================================
	def obtainDT(self):
		self.nowTime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		return self.nowTime

#===============================================================================================================================================
	def dictMinusOne(self, label):
		self.rate_limits[label]['remain'] = self.rate_limits[label]['remain'] - 1

#===============================================================================================================================================
	def getKeys(self):
		with open(os.path.join('Settings','keys')) as json_data: d = json.load(json_data)
		for key in self.keyFields: self.keys.append(d[key])

#===============================================================================================================================================
	def getAccounts(self):
		with open(os.path.join('Settings','accounts')) as accounts:
			for account in accounts:
				self.twitterAccounts.append(account.replace('\n',''))

#===============================================================================================================================================
	def getDBInfo(self):
		with open(os.path.join('Settings','psql')) as json_data: d = json.load(json_data)
		self.dbInfo['database'] = d['database']
		self.dbInfo['user'] = d['user']
		self.dbInfo['password'] = d['password']
		self.dbInfo['host'] = d['host']
		self.dbInfo['port'] = d['port']

#===============================================================================================================================================
	def getEmailSettings(self):
		with open(os.path.join('Settings','email')) as json_data: d = json.load(json_data)
		self.fromAddr = d['fromAddress']
		self.toAddr = d['toAddress']
		self.emailPass = d['emailPassword']
		self.targetTime = d['reportHours']

#===============================================================================================================================================
	# Helper function for checkRates()
	def fillDict(self, dictKey, jsonData):
		self.rate_limits[dictKey]['limit'] = jsonData['limit']
		self.rate_limits[dictKey]['remain'] = jsonData['remaining']

#=========================================================================================================================
	def isEmptyList(self, theList):
		return (theList==[])

#=========================================================================================================================
	def getTimeStamp(self, theRecord):
		# The record is the returned tuple from SELECT and has 4 items
		return datetime.datetime.strptime(str(theRecord[1])+' '+str(theRecord[2]), '%Y-%m-%d %H:%M:%S')

#===============================================================================================================================================
	def parseTimeStamp(self, timeString):
		return (datetime.datetime.strptime(timeString, '%Y-%m-%dT%H:%M:%SZ'))

#===============================================================================================================================================
	def parseDT(self, timeString):
		return (datetime.datetime.strptime(timeString, '%Y-%m-%d %H:%M:%S'))

#===============================================================================================================================================
	def parseTime(self, timeString):
		return (datetime.datetime.strptime(timeString, '%H:%M:%S'))
		# print(datetime.datetime.strptime('2017-06-09T06:12:47Z', '%Y-%m-%dT%H:%M:%SZ'))

#===============================================================================================================================================
	def resetCheck(self):
		return (self.parseDT(self.obtainDT())>=self.parseDT(self.resetTime))
		# return (self.parseTime(self.obtainTime())>=self.parseTime(self.resetTime))

#===============================================================================================================================================
	def timeDiff(self, wakeTime, maxSleep):
		return max(0, maxSleep - int((self.parseDT(self.obtainDT())-self.parseDT(wakeTime)).total_seconds()))

#===============================================================================================================================================
	def getLocations(self):
		results = requests.get(self.available_url, auth=OAuth1(self.keys[0],self.keys[1],self.keys[2],self.keys[3])).json()
		for result in results:
			self.cur.execute("SELECT * FROM locations where locationid=%s", (result['woeid'],))
			if (self.cur.fetchone()==None):
				countryName = 'N/A' if (result['woeid']==1) else result['country']
				self.cur.execute("INSERT INTO locations (locationid, cityname, country) VALUES (%s,%s,%s)", (result['woeid'],result['name'],countryName))
		self.conn.commit()

#===============================================================================================================================================
	def checkRates(self):
		result = requests.get('https://api.twitter.com/1.1/application/rate_limit_status.json', auth=OAuth1(self.keys[0],self.keys[1],self.keys[2],self.keys[3]))
		rateData = result.json()['resources']
		self.fillDict('search_tweets', rateData['search']['/search/tweets'])
		self.fillDict('user_timeline', rateData['statuses']['/statuses/user_timeline'])
		self.fillDict('trends_place', rateData['trends']['/trends/place'])
		self.resetTime = datetime.datetime.fromtimestamp(int(rateData['search']['/search/tweets']['reset'])).strftime('%Y-%m-%d %H:%M:%S')

#===============================================================================================================================================
	def readableRates(self):
		print('User Timeline Remain: %s' % self.rate_limits['user_timeline']['remain'])
		print('Tweets Search Remain: %s' % self.rate_limits['search_tweets']['remain'])
		print('Trending Tags Remain: %s' % self.rate_limits['trends_place']['remain'])

#===============================================================================================================================================
	def emailReport(self, imageMode, timeID):
	 
		msg = MIMEMultipart('Related')
		msg['From'] = self.fromAddr
		msg['To'] = self.toAddr
		msg['Subject'] = 'Notification: News From Twitter'
		msg.preamble = 'Notification: News From Twitter'

		imageMsg = ['Trend for last hour:', 'Trending for the last 24 hours:', 'Current top 5 trending tags:']
		eImages = []
		description = []
		for i in range(0,3):
			if (imageMode & pow(2,i)): eImages.append(i+1)

		if (imageMode==0):
			msg.attach(MIMEText('I\'m sorry but something wrong happened', 'plain'))
		else:
			for eImage in eImages:
				description.append('<b>%s</b><br><img src="cid:image%s"><br><br>' % (imageMsg[eImage-1], eImage))
			msgText = MIMEText(''.join(description), 'html')
			msg.attach(msgText)

			for eImage in eImages:
				# This example assumes the image is in the current directory
				imageName = str(timeID)+'-Trending-%s.png' % eImage
				fp = open(os.path.join('Charts', imageName), 'rb')
				msgImage = MIMEImage(fp.read())
				fp.close()

				# Define the image's ID as referenced above
				imageHeader = '<image%s>' % eImage
				msgImage.add_header('Content-ID', imageHeader)
				msg.attach(msgImage)

		# Send the email (this example assumes SMTP authentication is required)
		server = smtplib.SMTP('smtp.gmail.com', 587)
		server.starttls()
		server.login(self.fromAddr, self.emailPass)
		server.sendmail(self.fromAddr, self.toAddr, msg.as_string())
		server.quit()

#=========================================================================================================================
	def selectTrendTags(self, firstData, secondData, mode):
		thisCur = self.conn.cursor()
		thisCur.execute("SELECT tagname, trending.tagid, trending.datetimeid FROM trending INNER JOIN hashtag ON trending.tagid=hashtag.tagid WHERE trending.datetimeid=%s OR trending.datetimeid=%s GROUP BY tagname, trending.tagid, trending.datetimeid ORDER BY max(volume) DESC;", (firstData[0],secondData[0]))
		results = [[r[0].strip(), r[1], r[2]] for r in thisCur.fetchall() if (self.includeAFK or not langdetect.detect(r[0]) in ['ar', 'fa', 'ka'])]
		lastTags = [r[0] for r in results if (r[2]==firstData[0])]
		firstTags = [r[0] for r in results if (r[2]==secondData[0])]
		if (mode==1): targetTags = [tag for tag in (set(lastTags) ^ set(firstTags)) if (tag in lastTags)]
		if (mode==2): targetTags = list(set(lastTags) & set(firstTags))
		if (mode==3): targetTags = list(set(lastTags))
		noTarget = self.isEmptyList(targetTags)
		if (not noTarget): self.plotTrend([r for r in results if (r[0] in targetTags)][:5],secondData[0], mode, firstData[0])
		thisCur.close()
		return noTarget

#=========================================================================================================================
	def plotTrend(self, theTrends, startTimeID, mode, timeID):
		lineColours = {0:'red', 1:'blue', 2:'purple', 3:'green', 4:'lime'}
		pCur = self.conn.cursor()
		theColour = 0
		barDict = {}
		fig, ax = plt.subplots(facecolor='lightslategray')
		# ax.set_axis_bgcolor('lightslategray') # Deprecated in version 2.0
		ax.set_facecolor('lightslategray')
		# ax.set_xlim(0,24)
		# ax.set_ylim(0,100000)
		# fig.suptitle('Hashtag Trends', fontsize=20)
		plt.xlabel('Time', fontsize=12)
		plt.ylabel('Volume', fontsize= 12)

		for theTrend in theTrends:

			if (mode==3):
				pCur.execute("SELECT volume FROM trending INNER JOIN datetimelist ON trending.datetimeid=datetimelist.datetimeid WHERE trending.datetimeid>=%s AND trending.tagid=%s", (startTimeID, theTrend[1]))
				theData = pCur.fetchone()
				barDict[theTrend[0]] = theData[0]
			else:
				pCur.execute("SELECT volume, trendtime FROM trending INNER JOIN datetimelist ON trending.datetimeid=datetimelist.datetimeid WHERE trending.datetimeid>=%s AND trending.tagid=%s", (startTimeID, theTrend[1]))
				theData = pCur.fetchall()
				#-----------------------------------------------------------------------------------
				theData = [item for item in zip(*theData)]
				theData[0] = tagRates = [rateOne - rateTwo for rateOne, rateTwo in zip(theData[0][1:], theData[0])]
				theData[1] = [tagTime.hour for tagTime in theData[1][1:]]
				timeData = [[tagTime,0] for tagTime in set(theData[1])]
				theData = [item for item in zip(*theData)]
				for thisTime in timeData:
					for thisData in theData:
						if (thisData[1]==thisTime[0]): thisTime[1] = thisTime[1] + thisData[0]
				theData = [item for item in zip(*timeData)]
				#-----------------------------------------------------------------------------------
				theData = pd.DataFrame(data={'Rate' : theData[1], 'Date' : theData[0]}, columns=['Rate', 'Date'])
				ax.plot(theData['Date'], theData['Rate'], color=lineColours[theColour], label=theTrend[0], marker='o')
				# ax.plot(theData['Date'], theData['Rate'], color=lineColours[theColour], label=theTrend[0])
				theColour = theColour + 1

		if (mode==3):
			plt.xticks(fontsize=7)
			plt.yticks(fontsize=7)
			# y_pos = np.arange(len(barDict))
			# barList = ax.bar(y_pos,barDict.values(),align='center',alpha=0.5)#,tick_label=set(barDict.keys()))
			barList = ax.bar(range(len(barDict)),barDict.values(),align='center',alpha=0.5,tick_label=set(barDict.keys()))
			for colour in range(0,5): barList[colour].set_color(lineColours[colour])
			ax.set_xlabel('Hashtag')
			fig.autofmt_xdate()
		else:
			x1,x2,y1,y2 = plt.axis()
			ax.axis((x1,x2,0,y2))
			legend = ax.legend(loc='lower center', shadow=True, framealpha=0.8, bbox_to_anchor=(0,0.98,1,1), mode='expand', ncol=3)
			for label in legend.get_texts(): label.set_fontsize(7)
		fig.savefig(os.path.join('Charts', str(timeID)+'-Trending-'+str(mode)+'.png'))
		fig.clf()
		pCur.close()

#=========================================================================================================================
	def getTopTrends(self):
		
		thisCur = self.conn.cursor()

		thisCur.execute("SELECT * FROM datetimelist ORDER BY datetimeid DESC LIMIT 288")
		allTS = thisCur.fetchall()
		noTarget = False
		imageMode = 0

		if (len(allTS) >= 12):
			lastTime = self.getTimeStamp(allTS[0])
			if (datetime.datetime.utcnow() - lastTime <= datetime.timedelta(minutes=10, seconds=30)):

				firstTime = self.getTimeStamp(allTS[11])
				# Try plot trends from the past hour
				if (lastTime - firstTime < datetime.timedelta(hours=1, minutes=20)):
					noTarget = self.selectTrendTags(allTS[0],allTS[11],1)
					if (noTarget==False): imageMode = 1

				# Try plot trends from the past 24 hours
				buffTime = self.getTimeStamp(allTS[1])
				if (lastTime-buffTime < datetime.timedelta(days=1,minutes=5)):
					dtItem = min(287, len(allTS))
					buffTime = self.getTimeStamp(allTS[dtItem])
					# Find the max range of datetime records
					while(lastTime-buffTime > datetime.timedelta(days=1,minutes=5)):
						dtItem = dtItem - 1
						buffTime = self.getTimeStamp(allTS[dtItem])
					# noTarget = noTarget or selectTrendTags(allTS[0],allTS[dtItem],2)
					noTarget = self.selectTrendTags(allTS[0],allTS[dtItem],2)
					if (noTarget==False): imageMode ^= 2

				# If either of above don't have enough data, plot tweet volume for current top 5 trending
				if (imageMode<3):
					self.selectTrendTags(allTS[0],allTS[0],3)
					imageMode += 4

				self.emailReport(imageMode, allTS[0][0])

		thisCur.close()

#===============================================================================================================================================
	def tagsExist(self, results):
		allTagID = []
		thisCursor = self.conn.cursor()
		for result in results:
			rTag = result.replace('#', '')[:25]
			thisCursor.execute("SELECT * FROM Hashtag where tagName=%s", (rTag,))
			hasID = thisCursor.fetchone()
			if (hasID is None):
				thisCursor.execute("INSERT INTO Hashtag (tagName) VALUES (%s) RETURNING tagID", (rTag,))
				self.conn.commit()
				hasID = thisCursor.fetchone()
			allTagID.append(hasID[0])		
		thisCursor.close()
		return allTagID

#===============================================================================================================================================
	def trendingTags(self, locationID=1):
		parameters = {'id' : str(locationID)}
		results = requests.get(self.trends_place_url, auth=OAuth1(self.keys[0],self.keys[1],self.keys[2],self.keys[3]), params=parameters)
		timeStamp = str(self.parseTimeStamp(results.json()[0]['created_at'])).split(' ')
		trendLocation = results.json()[0]['locations']
		self.tCur.execute("SELECT DateTimeID FROM DateTimeList WHERE trendDate=%s AND trendTime=%s", (timeStamp[0],timeStamp[1]))
		sessionTimeID = self.tCur.fetchone()
		if (sessionTimeID==None):
			self.tCur.execute("INSERT INTO DateTimeList (trendDate, trendTime) VALUES (%s,%s) RETURNING DateTimeID", (timeStamp[0],timeStamp[1]))
			sessionTimeID = self.tCur.fetchone()
			self.conn.commit()
		sortedResults = sorted([[result['tweet_volume'], result['name'], result['query']] for result in results.json()[0]['trends']  if result['tweet_volume'] is not None], reverse=True)

		tagNames = [sortedResult[1] for sortedResult in sortedResults]
		tagIDs = self.tagsExist(tagNames)

		self.tCur.execute("SELECT * FROM locations where LocationID=%s", (trendLocation[0]['woeid'],))
		locationInfo = self.tCur.fetchone()[0]

		for k, result in enumerate(sortedResults):
			self.tCur.execute("INSERT INTO Trending (DateTimeID, LocationID, Volume, tagID) VALUES (%s, %s, %s, %s)", (sessionTimeID[0], locationInfo, result[0], tagIDs[k]))
		self.conn.commit()

		for tagName in tagNames:
			if (self.rate_limits['search_tweets']['remain']>0):
				self.searchTag(tagName.replace('#', '')[:25])
				self.dictMinusOne('search_tweets')

#===============================================================================================================================================
	def searchTag(self, keyword):
		parameters = {'q' : keyword, 'count' : 100, 'tweet_mode' : 'extended'}
		results = requests.get(self.tweet_search_url, auth=OAuth1(self.keys[0],self.keys[1],self.keys[2],self.keys[3]), params=parameters)
		results = results.json()
		for result in results['statuses']:
			userInfo = [result['user']['id'], result['user']['screen_name']]
			self.tCur.execute("SELECT * FROM TUser where UID=%s", (userInfo[0],))
			#Use try except
			if (self.tCur.fetchone()==None): self.tCur.execute("INSERT INTO TUser (UID, ScreenName) VALUES (%s, %s)", (userInfo[0], userInfo[1]))
			self.tCur.execute("SELECT * FROM Tweets where TID=%s", (result['id'],))
			if (self.tCur.fetchone()==None):
				tStamp = str(datetime.datetime.strptime(result['created_at'], '%a %b %d %H:%M:%S +0000 %Y')).split(' ')
				hasRT = True if ('retweeted_status' in result) else False
				tContent = result['retweeted_status']['full_text'] if (hasRT) else result['full_text']
				self.tCur.execute("INSERT INTO Tweets (TID, UID, tweetDate, tweetTime, tweetText, FCount, RCount) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING RID", (result['id'], result['user']['id'], tStamp[0], tStamp[1], tContent.replace('\'','\'\''), result['favorite_count'], result['retweet_count']))
				self.conn.commit()
				resourceID = self.tCur.fetchone()[0]
				target = result['retweeted_status'] if (hasRT) else result
				for url in target['entities']['urls']:
					self.tCur.execute("INSERT INTO URL (RID, link) VALUES (%s, %s)", (resourceID, url['url']))
				tagIDs = self.tagsExist([hashtag['text'] for hashtag in target['entities']['hashtags']])
				for tagID in tagIDs:
					self.tCur.execute("INSERT INTO TweetTags (RID, tagID) VALUES (%s, %s)", (resourceID, tagID))
				self.conn.commit()

#===============================================================================================================================================
	def userTimeline(self, screenName):
		parameters = {'screen_name' : screenName, 'count' : 200, 'tweet_mode' : 'extended'}
		results = requests.get('https://api.twitter.com/1.1/statuses/user_timeline.json', auth=OAuth1(self.keys[0],self.keys[1],self.keys[2],self.keys[3]), params=parameters).json()
		try:
			userInfo = [results[0]['user']['id'], results[0]['user']['screen_name']]
			self.uCur.execute("SELECT * FROM TUser where UID=%s", (userInfo[0],))
			if (self.uCur.fetchone()==None):
				self.uCur.execute("INSERT INTO TUser (UID, ScreenName) VALUES (%s, %s)", (userInfo[0], userInfo[1]))
				self.conn.commit()
			for result in results:
				self.uCur.execute("SELECT * FROM Tweets where TID=%s", (result['id'],))
				if (self.uCur.fetchone()==None):
					tStamp = str(datetime.datetime.strptime(result['created_at'], '%a %b %d %H:%M:%S +0000 %Y')).split(' ')
					hasRT = True if ('retweeted_status' in result) else False
					tContent = result['retweeted_status']['full_text'] if (hasRT) else result['full_text']
					self.uCur.execute("INSERT INTO Tweets (TID, UID, tweetDate, tweetTime, tweetText, FCount, RCount) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING RID", (result['id'], result['user']['id'], tStamp[0], tStamp[1], tContent.replace('\'','\'\''), result['favorite_count'], result['retweet_count']))
					self.conn.commit()
					resourceID = self.uCur.fetchone()[0]
					target = result['retweeted_status'] if (hasRT) else result
					for url in target['entities']['urls']:
						self.uCur.execute("INSERT INTO URL (RID, link) VALUES (%s, %s)", (resourceID, url['url']))
					tagIDs = self.tagsExist([hashtag['text'] for hashtag in target['entities']['hashtags']])
					for tagID in tagIDs:
						self.uCur.execute("INSERT INTO TweetTags (RID, tagID) VALUES (%s, %s)", (resourceID, tagID))
					self.conn.commit()
		except:
			print('Problem when handling user: %s' % screenName)

#===============================================================================================================================================
	def getRates(self, sleepTime=60):
		while (True):
			self.checkRates()
			time.sleep(sleepTime)

#===============================================================================================================================================
	def getTrending(self, sleepTime=300, targetID=1):
		while (True):
			wakeTime = self.obtainDT()
			try:
				if (self.resetCheck()): self.checkRates()
				if (self.rate_limits['trends_place']['remain']>0):
					print('[%s][%s] Trending search' % (self.obtainDT(), 'Start'))
					# print('Trending Tags Executed at: %s' % self.obtainTime())
					self.trendingTags(targetID)
					self.dictMinusOne('trends_place')
				print('[%s][%s] Trending search' % (self.obtainDT(), '*End*'))
			except:
				print('[%s][%s] Trending search' % (self.obtainDT(), 'Error'))
			time.sleep(self.timeDiff(wakeTime, sleepTime))

#===============================================================================================================================================
	def getTimeline(self, sleepTime=900):
		while (True):
			wakeTime = self.obtainDT()
			self.getAccounts()
			try:
				if (self.resetCheck()): self.checkRates()
				print('[%s][%s] Timeline search' % (self.obtainDT(), 'Start'))
				for twitterAccount in self.twitterAccounts:
					if (self.rate_limits['user_timeline']['remain']>0):
						self.userTimeline(twitterAccount)
						self.dictMinusOne('user_timeline')
				print('[%s][%s] Timeline search' % (self.obtainDT(), '*End*'))
			except:
				print('[%s][%s] Timeline search' % (self.obtainDT(), 'Error'))
			time.sleep(self.timeDiff(wakeTime, sleepTime))

#===============================================================================================================================================
	def getTrendSummary(self, sleepTime=1800):
		# Schedule for specific time of day to run
		toReport = True
		while (True):
			wakeTime = self.obtainDT()
			self.getEmailSettings()
			try:
				currentTime = self.parseDT(wakeTime)
				if (currentTime.hour in self.targetTime):
					if (toReport):
						print('[%s][%s] Trending Report' % (self.obtainDT(), 'Start'))
						self.getTopTrends()
						toReport = False
						print('[%s][%s] Trending Report' % (self.obtainDT(), '*End*'))
				else:
					if (not toReport): toReport = True
					sleepTime = 900 if (currentTime.hour+1 in self.targetTime) else 1800
			except:
				print('[%s][%s] Trending Report' % (self.obtainDT(), 'Error'))
			
			# Sleep until the next schedule time
			time.sleep(self.timeDiff(wakeTime, sleepTime))

#===============================================================================================================================================
bird = tweetCollect()
