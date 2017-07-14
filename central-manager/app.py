# -*- coding: utf-8 -*-
from configparser import ConfigParser
from datetime import datetime
from threading import Thread

import urllib.request
import pymysql
import pexpect
import json


# load config file
config = ConfigParser()
config.read('config.ini')
err_type = ''
log_file = ''
db_host = ''
db_port = 0
db_user = ''
db_pass = ''
db_name = ''
db_prefix = ''
interval_time = 0
try:
    # log values
    err_type = 'Log > URL'
    log_file = config.get('Log', 'URL')

    # database values
    err_type = 'Storage > Host'
    db_host = config.get('Storage', 'Host')
    err_type = 'Storage > Port'
    db_port = config.get('Storage', 'Port')
    err_type = 'Storage > User'
    db_user = config.get('Storage', 'User')
    err_type = 'Storage > Password'
    db_pass = config.get('Storage', 'Password')
    err_type = 'Storage > Database'
    db_name = config.get('Storage', 'Database')
    err_type = 'Storage > Prefix'
    db_prefix = config.get('Storage', 'Prefix')
	
	# collector
	interval_time = config.getint('Collector', 'Interval')
except IOError:
    print('CONFIG ERROR: Unable to load values from \"{}\"!'.format(err_type))
    print('CONFIG ERROR: Force closing program...')
    exit()


# prepare log file
try:
    logger = open(config.get('Log', 'URL'))
except IOError:
    print('FILE ERROR: Unable to open file: {}!'.format(config.get('Log', 'URL')))
    print('FILE ERROR: Force closing program...')
    exit()


# prepare database connection
con = None
cur = None


# log errors/debugging
def log(service, typ, msg):
    now = datetime.now()
    log_msg = '{} [{:^12}]: {}\r\n'.format(now.strftime('%m-%d-%Y %H:%M:%S'),
                                           service + ' ' + typ,
                                           msg)

    # print to console
    print(log_msg)
    try:
        logger.write(log_msg)
    except IOError as e:
        print('FILE ERROR: Unable to write log to file! Reason: {}'.format(e.args[0]))


# ping test server
def ping_server(host):
    # ping server
    result = pexpect.spawn('ping -c 1 {}'.format(host))

    try:
        # retrieve ping time
        p = result.readline()
        time_ping = float(p[p.find('time=') + 5:p.find(' ms')])

        # ping time
        return time_ping
    except ValueError:
        # ping time
        return -1


# insert new ping data to SQL database
def insert_ping_data(server_id, status, ping=None):
    try:
        cur.execute('INSERT INTO {}_ping_logs (server_id, status, ping) '
                    'VALUES (?, ?, ?)'.format(db_prefix), server_id, status, ping)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [memory] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# insert new memory data to SQL database
def insert_memory_data(server_id, status, ram_percent=None, ram_used=None, ram_total=None, swap_percent=None,
                       swap_used=None, swap_total=None):
    try:
        cur.execute('INSERT INTO {}_memory_logs (server_id, status, ram_percent, ram_used, ram_total, swap_percent, '
                    'swap_used, swap_total) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'.format(db_prefix), server_id, status, ram_percent, ram_used,
                    ram_total, swap_percent, swap_used, swap_total)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [memory] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# insert new CPU data to SQL database
def insert_cpu_data(server_id, status, cpu_percent=None):
    try:
        cur.execute('INSERT INTO {}_cpu_logs (server_id, status, cpu_percent) '
                    'VALUES (?, ?, ?)'.format(db_prefix), server_id, status, cpu_percent)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [cpu] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# insert new network data to SQL database
def insert_net_data(server_id, status, name=None, sent=None, received=None):
    try:
        cur.execute('INSERT INTO {}_network_logs (server_id, status, name, sent, received) '
                    'VALUES (?, ?, ?, ?)'.format(db_prefix), server_id, status, name, sent, received)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [network] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# insert new network data to SQL database
def insert_load_data(server_id, status, one_avg=None, five_avg=None, fifteen_avg=None):
    try:
        cur.execute('INSERT INTO {}_load_logs (server_id, status, 1m_avg, 5m_avg, 15m_avg) '
                    'VALUES (?, ?, ?, ?, ?)'.format(db_prefix), server_id, status, one_avg, five_avg, fifteen_avg)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [load] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# insert new disk data to SQL database
def insert_disk_data(server_id, status, device=None, percent=None, used=None, total=None):
    try:
        cur.execute('INSERT INTO {}_disk_logs (server_id, status, device, percent, used, total) '
                    'VALUES (?, ?, ?, ?, ?, ?)'.format(db_prefix), server_id, status, device, percent, used, total)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [disk] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# insert new disk I/O data to SQL database
def insert_disk_io_data(server_id, status, io=None):
    try:
        cur.execute('INSERT INTO {}_disk-io_logs (server_id, status, io) '
                    'VALUES (?, ?, ?)'.format(db_prefix), server_id, status, io)
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Unable to insert [disk] data for server [{}] to SQL database! STACKTRACE: {}'
            .format(server_id, e.args))


# scrape data from each agent (server)
def scrape_data(time):
    while True:
        # retrieve list of servers
        servers = list()
        try:
            # get list of servers
            for row in cur.execute('SELECT * FROM {}_servers'.format(db_prefix)):
                servers.append(Server(row[0], row[1], row[2], row[3]))

            # go through each server and scrape data
            for serv in servers:
                ping_result = ping_server(serv.host)
                if ping_result is not -1:
                    try:
                        # sniff up data from a server
                        with urllib.request.urlopen('http://{}:{}/'.format(serv.host, serv.port)) as url:
                            data = json.loads(url.read().decode())

                            # insert data to SQL db
                            insert_ping_data(serv.id, 1, ping_result)
                            insert_memory_data(serv.id,
                                               1,
                                               data['memory']['ram']['percent_used'],
                                               data['memory']['ram']['used'],
                                               data['memory']['ram']['total'],
                                               data['memory']['swap']['percent_used'],
                                               data['memory']['swap']['used'],
                                               data['memory']['swap']['total'])
                            insert_cpu_data(serv.id,
                                            1,
                                            data['cpu']['percent_used'])
                            for net_nic in data['network']:
                                insert_net_data(serv.id,
                                                1,
                                                net_nic['name'],
                                                net_nic['mb_sent'],
                                                net_nic['mb_received'])
                            insert_load_data(serv.id,
                                             1,
                                             data['load']['1min'],
                                             data['load']['5min'],
                                             data['load']['15min'])

                            for disk in data['disks']['list']:
                                insert_disk_data(serv.id,
                                                 1,
                                                 disk['device'],
                                                 disk['percent_used'],
                                                 disk['used'],
                                                 disk['total'])
                            log('CM', 'DEBUG', 'Retrieved and logged data for server [{}]!'.format(serv.name))
                    except pymysql.Error:
                        log('AGENT', 'ERROR', 'Unable to access server [{}]! Please make sure the port is open on that '
                                              'server!'.format(serv.name))
                else:
                    insert_ping_data(serv.id, 0)
                    insert_memory_data(serv.id, 0)
                    insert_cpu_data(serv.id, 0)
                    insert_net_data(serv.id, 0)
                    insert_load_data(serv.id, 0)
                    insert_disk_data(serv.id, 0)
                    log('AGENT', 'WARN', 'Server [{}] is not responding, skipping...'.format(serv.name))
        except pymysql.Error as e:
            log('SQL', 'ERROR', 'Problem when trying to retrieve data from the server! STACKTRACE: {}'.format(e.args))
            log('SQL', 'ERROR', 'Force closing program...')
            exit()
        time.sleep(time)


# main "method"
if __name__ == '__main__':
    # check to make sure the database has the required tables
    try:
        # connect to the database
        con = pymysql.connect(host=db_host,
                              port=db_port,
                              user=db_user,
                              passwd=db_pass,
                              db=db_name)
        cur = con.cursor()

        # create/check servers table
		# types:
		# GN : General server
		# DB : Database server
		# EM : Email Server
		# WB : Website Server
		# FW : Firewall System
		# AD : Active Directory Server
		# VM : Virtual Machine/Hypervisor Server
		# FS : File Sharing Server
		# SY : Security-Based Server
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_servers (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
					type CHAR(2) NOT NULL,
                    hostname VARCHAR(255) NOT NULL,
                    port SMALLINT NOT NULL);""".format(db_prefix))

        # create/check ping logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_ping_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    ping DECIMAL(100,2));""".format(db_prefix))

        # create/check memory logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_memory_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    ram_percent DECIMAL(4,1),
                    ram_used DECIMAL(100,2),
                    ram_total DECIMAL(100,2),
                    swap_percent DECIMAL(4,1),
                    swap_used DECIMAL(100,2),
                    swap_total DECIMAL(100,2));""".format(db_prefix))

        # create/check CPU logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_cpu_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    cpu_percent DECIMAL(4,1));""".format(db_prefix))

        # create/check network logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_network_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    name VARCHAR(50),
                    sent BIGINT,
                    received BIGINT);""".format(db_prefix))

        # create/check load logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_load_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    1m_avg DECIMAL(5,1),
                    5m_avg DECIMAL(5,1),
                    15m_avg DECIMAL(5,1));""".format(db_prefix))

        # create/check disk logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_disk_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    device VARCHAR(50),
                    percent BIGINT,
                    used BIGINT,
                    total BIGINT);""".format(db_prefix))

        # create/check disk logs table
        cur.execute("""CREATE TABLE IF NOT EXISTS {}_disk-io_logs (
                    id BIGINT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    timestamp DATE DEFAULT GETDATE(),
                    status ENUM(0,1),
                    io DECIMAL(5,2));""".format(db_prefix))

        # submit changes to SQL server
        cur.commit()
    except pymysql.Error as e:
        log('SQL', 'ERROR', 'Error when trying to check/create table! STACKTRACE: {}'.format(e.args))
        log('SQL', 'ERROR', 'Force closing program...')
        exit()

    # start scraping thread job!
    thd = Thread(target=scrape_data, args=(interval_time))
    thd.daemon = True
    thd.start()


class Server:
    def __init__(self, _id, _name, _host, _port):
        self.id = _id
        self.name = _name
        self.host = _host
        self.port = _port

    def get_id(self):
        return self.id

    def get_name(self):
        return self.name

    def get_host(self):
        return self.host

    def get_port(self):
        return self.port
