# -*- coding: utf-8 -*-
from configparser import ConfigParser
from flask import Flask, jsonify, request
import logging.handlers
import logging

from bin.ram import RAM
from bin.cpu import CPU
from bin.network import Network
from bin.load_avg import LoadAvg
from bin.boot_time import BootTime
from bin.disk import Disk


# convert human sizes to bytes
def convert_bytes(byts):
    try:
        byts = byts.lower()
        if byts.endswith('kb'):
            return int(byts[0:-2]) * 1024
        elif byts.endswith('mb'):
            return int(byts[0:-2]) * 1024 * 1024
        elif byts.endswith('gb'):
            return int(byts[0:-2]) * 1024 * 1024 * 1024
        
        #for anything else... just throw an exception, we care zero
        raise IOError('Invalid input. Correct format: #kb/#mb/#gb like 10gb or 5mb')
        
    except Exception as error :
        raise Exception ('Invalid input. Correct format: #kb/#mb/#gb like 10gb or 5mb. An error '+  + repr(error) + 'occured')


# load config
config = ConfigParser()
config.read('config.ini')
err_type = ''
log_file = ''
log_size_limit = ''
log_file_number_limit = 0
flsk_host = ''
flsk_port = 0
try:
    # log values
    err_type = 'Log > Name'
    log_file = config.get('Log', 'Name', fallback='agent.log')
    err_type = 'Log > Size_limit'
    log_size_limit = config.get('Log', 'Size_limit', fallback='5mb')
    log_size_limit = convert_bytes(log_size_limit)
    err_type = 'Log > File_Limit'
    log_file_number_limit = config.getint('Log', 'File_Limit', fallback=10)

    # flask values
    err_type = 'Flask > Host'
    flsk_host = config.get('Flask', 'Host', fallback='0.0.0.0')
    err_type = 'Flask > Port'
    flsk_port = config.getint('Flask', 'Port', fallback=5000)
except IOError as e:
    print('CONFIG ERROR: Unable to load values from \"{}\"! STACKTRACE: {}'.format(err_type, e.args[1]))
    print('CONFIG ERROR: Force closing program...')
    exit()


# prepare logging
try:
    logger = logging.getLogger('AtomicMonitor Agent')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.handlers.RotatingFileHandler(log_file, maxBytes=log_size_limit,
                                                           backupCount=log_file_number_limit))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(topic)-5s | %(message)s'))
    logger.addHandler(ch)
except IOError as e:
    print('FILE ERROR: Unable to prepare log file! STACETRACE: {}'.format(e.args[1]))
    print('FILE ERROR: Force closing program...')
    exit()


# setup variables
sram = RAM()
scpu = CPU()
net = Network()
load = LoadAvg()
boot = BootTime()
sdisk = Disk()
app = Flask(__name__)


# display current specs
@app.route('/now')
def web_now():
    # retrieve current system specs
    ram_percent, ram_used, ram_total = sram.get_memory_usage()
    cpu_percent = scpu.get_usage()
    boot_time = boot.get_boot_time()
    disk_io = sdisk.get_disk_io()

    # create json object
    json_data = {
        'ram': {
            'percent_used': ram_percent,
            'used': ram_used,
            'total': ram_total
        },
        'cpu': {
            'percent_used': cpu_percent
        },
        'boot': {
            'start_timestamp': boot_time
        },
        'disk_io': disk_io
    }

    logging.info('Retrieved now status for IP: {}'.format(request.remote_addr), extra={'topic': 'AGENT'})

    # print json data
    return jsonify(json_data)


# display full system specs
@app.route('/')
def web_all():
    # retrieve current system specs
    ram_percent, ram_used, ram_total = sram.get_memory_usage()
    swap_percent, swap_used, swap_total = sram.get_swap_usage()
    cpu_usage = scpu.get_usage()
    nics_bytes = net.get_nic_status()
    nic_names, nic_sent, nic_recvs = [], [], []
    for nic in nics_bytes:
        nic_names.append(nic.get_name())
        nic_sent.append(nic.get_sent())
        nic_recvs.append(nic.get_recv())
    islinux, load_1m, load_5m, load_15m = load.get_load()
    if not islinux:
        load_1m = 'NULL'
        load_5m = 'NULL'
        load_15m = 'NULL'
    boot_time = boot.get_boot_time()
    disks = sdisk.get_disks()
    disk_names, disk_percents, disk_uses, disk_totals = [], [], [], []
    for disk in disks:
        disk_names.append(disk.get_name())
        disk_percents.append(disk.get_percent())
        disk_uses.append(disk.get_used())
        disk_totals.append(disk.get_total())
    disk_io = sdisk.get_disk_io()

    # create json object
    json_data = {
        'memory': {
            'ram': {
                'percent_used': ram_percent,
                'used': ram_used,
                'total': ram_total
            },
            'swap': {
                'percent_used': swap_percent,
                'used': swap_used,
                'total': swap_total
            }
        },
        'cpu': {
            'percent_used': cpu_usage
        },
        'network': [
            {
                'name': name,
                'mb_sent': sent,
                'mb_recieved': recv
            }
            for name, sent, recv in zip(nic_names, nic_sent, nic_recvs)
        ],
        'load': {
            '1min': load_1m,
            '5min': load_5m,
            '15min': load_15m
        },
        'boot': {
            'time': {
                'timestamp': boot_time
            }
        },
        'disks': {
            'io': disk_io,
            'list': [
                {
                    'name': name,
                    'percent_used': percent,
                    'used': used,
                    'total': total
                }
                for name, percent, used, total in zip(disk_names, disk_percents, disk_uses, disk_totals)
            ]
        }
    }

    logging.info('Retrieved all status for IP: {}'.format(request.remote_addr), extra={'topic': 'AGENT'})

    # print json data
    return jsonify(json_data)


# start flask process
if __name__ == '__main__':
    logging.info('Starting program...', extra={'topic': 'AGENT'})

    # start Flask service
    app.run(host=flsk_host, port=flsk_port)
