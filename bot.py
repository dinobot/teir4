import urllib2, threading, json
import xml.etree.ElementTree as ET
from flask import Flask, request
from flask_apscheduler import APScheduler
from unidecode import unidecode
from pytz import timezone
from datetime import datetime
import os
import conf

class Config(object):
    JOBS = [
        {
            'id': 'set_presence',
            'func': 'bot:keepalive',
            'trigger': 'interval',
            'seconds': 740
        },
        {
            'id': 'export_stats',
            'func': 'bot:query_stats',
            'trigger': 'interval',
            'seconds': 60
        }
    ]

    SCHEDULER_API_ENABLED = True

bot_id = conf.bot_id
bot_cr = conf.bot_cr
server = conf.server
team = conf.team

blacklist = conf.blacklist
os.environ['blacklist'] = str(json.dumps(blacklist))

#bot_presence_message = 'happy to serve'
bot_presence_message = conf.bot_presence_message

hook_url = conf.hook_url

def query_stats():
    try:
      b = json.loads(os.environ['blacklist'])
    except:
      b = []
    print 'query stats', b
    query_data = 'xmlMessage=<message type="contact.get.list" id="'+bot_id+'" password="'+bot_cr+'" />'
    req = urllib2.Request(server, query_data)
    q_response_xml_root = ET.fromstring(urllib2.urlopen(req).read())
   
    q_stats = {} 
    for i in q_response_xml_root.findall('contact'):
      print i.get('id')
      if i.get('id') in team.keys() and i.get('id') not in b:
        q_stats[i.get('id')] = {'name': str(i.get('firstname') +' ' + i.get('lastname')), 'status': i.get('presenceState'), 'login': i.get('firstname')[:1].lower()+i.get('lastname').lower()}
    os.environ['stats'] = str(json.dumps(q_stats))
    print 'synced_stats', q_stats
    return q_stats

def ping(m, message=''):
  r = 'xmlMessage=<message type="contact.send.message" id="'+bot_id+'" password="'+bot_cr+'" contactId="'+m+'"> <statement from="'+bot_id+'" to="'+m+'" text="'+message+'"/></message>'
  req = urllib2.Request(server, r)
  print m, urllib2.urlopen(req).code
    
def threaded_ping():
  threads = [threading.Thread(target=ping, args=(m,)) for m in team.keys() if m not in blacklist]
  for thread in threads:
    thread.start()
  for t in threads:
    thread.join()

def set_presence():
  r = 'xmlMessage=<message type="presence.select" id="'+bot_id+'" password="'+bot_cr+'" presenceState="bot-green" presenceAvailability="available" presenceMessage="'+bot_presence_message+'" />'
  req = urllib2.Request(server, r)
  print 'setting presence:', urllib2.urlopen(req).code

def keepalive():
  try:
    b = json.loads(os.environ['blacklist'])
    s = json.loads(os.environ['stats'])
  except:
    b = []
    s = []
  print 'keepalive blacklist', b
  set_presence()
  for m in team:
    if (m not in s) and (m not in b):
      ping(m)
      print 'pinging', m
  #os.environ['stats'] = str(json.dumps(stats))
  #if len(stats) == 0:
  #  threaded_ping()
  print s
  for attuid in s:
    h = int(datetime.now(team[attuid]).strftime('%H'))
    d = str(datetime.now(team[attuid]).strftime('%A'))
    if s[attuid]['status'] == 'offline' and attuid not in b:
      print attuid,'offline', h, d
      if h in xrange(9,17) and d not in ('Saturday', 'Sunday'):
        print 'notifying!'
        rdata = json.dumps({"username": 'T4 robo-nanny',
                            "icon_emoji": ':robot_face:',
                            "text":  '<@%s> log into Q! :computer:' % s[attuid]['login']
                           })
        r = urllib2.Request(hook_url, rdata)
        urllib2.urlopen(r)

query_stats()
keepalive()

if __name__ == '__main__':
  app = Flask(__name__)
  app.config.from_object(Config())
  scheduler = APScheduler()
  scheduler.init_app(app)
  scheduler.start()

  @app.route('/', methods=['GET'])
  def handle():
    stats = query_stats()
    request_data = unidecode(request.args.get('text', ''))
    response_url = str(request.args.get('response_url', ''))
    if request_data:
      key = request_data.split()[0]
      if key in team.keys():
        ping(key, ' '.join(request_data.split()[1:]))
        return '', 204
      if ''.join(request_data.split()[1:]) in team.keys():
        attuser = ''.join(request_data.split()[1:])
        if key == 'blacklist':
          if attuser not in blacklist:
            blacklist.append(attuser)
            os.environ['blacklist'] = str(json.dumps(blacklist))
            return '{"response_type": "in_channel", "text": "*'+attuser+'* blacklisted" }', 200, {'Content-Type': 'application/json'}
          else:
            return '', 203
        if key == 'whitelist':
          if attuser in blacklist:
            blacklist.remove(attuser) 
            os.environ['blacklist'] = str(json.dumps(blacklist))
            return '{"response_type": "in_channel", "text": "*'+attuser+'* whitelisted" }', 200, {'Content-Type': 'application/json'}
          else:
            return '', 203
      if key == 'team':
        return '{"response_type": "in_channel", "text": "'+(', '.join(team))+'"}', 200, {'Content-Type': 'application/json'}
      if key == 'help':
        return '{"response_type": "in_channel", "text": "*Commands*: \n   whitelist %attuuid% \n   blacklist %attuuid% \n   team \n *Send message*: \n   %attuuid% arbitary text (double quotes not accepted)" }', 200, {'Content-Type': 'application/json'}

    else:
      m = ''
      r = {}
      for uid in sorted(stats):
        name = stats[uid]['name']
        status = stats[uid]['status']
        login = stats[uid]['login']
        m = m + ((uid + ' ' + '`' + status +'`' + '\n') if status == "offline" else  (name + ' ' + '*' + status + '*' + '\n'))
      r['text'] = m if not blacklist else m + '\n _blacklisted:_ ' + ', '.join(blacklist)
      r['response_type'] = 'in_channel'
      return json.dumps(r), 200, {'Content-Type': 'application/json'}
  app.run(host='127.0.0.1', port=5002)   
