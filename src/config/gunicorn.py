import multiprocessing
import os

bind = '0.0.0.0:8000'
# bind = "127.0.0.1:8000"
workers = os.environ.get('GUNICORN_WORKERS', 5)
name = os.environ.get('PROJECT_NAME')
log_level = 'info'
log_file = '-'
pythonpath = '/app/'
forwarded_allow_ips = '*'
