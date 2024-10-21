#!/usr/bin/env python

import os
import json
import requests
import argparse
import re
import typing


JSON_HEADERS = {
  'Accept'       : 'application/json',
  'Content-Type' : 'application/json',
}
STATUSES = [ 'aborted', 'broken', 'done', 'failed', 'finished' ]
JOB_ID_RGX = re.compile(r'/\.(\d+)$')


def get_CRIC_name() -> str:
  capath = os.getenv('X509_CERT_DIR')
  cert = os.getenv('X509_USER_PROXY')
  key = cert
  url = 'https://cms-cric.cern.ch/api/accounts/user/query'
  params = {
    'json'   : True,
    'preset' : 'whoami',
  }
  r = requests.get(url, verify = capath, cert = (cert, key), params = params)
  j = json.loads(r.text)
  name = j['result'][0]['name'] # for username use 'login'
  return name


def get_json_request(r) -> dict:
  data = {}
  try:
    r.raise_for_status()
    content_type = r.headers.get('Content-Type')
    if 'application/json' in content_type:
      try:
        data = r.json()
      except ValueError:
        print('Response is not valid JSON')
    else:
      print('Unexpected Content-Type:', content_type)
  except requests.exceptions.HTTPError as err:
    print('HTTP error occurred:', err)
  except requests.exceptions.RequestException as err:
    print('Request error occurred:', err)
  return data


def pbook(name: str, contains: str = '', status: str = '', days: int = 14) -> dict:
  url = 'https://bigpanda.cern.ch/tasks'
  params = {
    'username' : name,
    'days'     : days,
    'json'     : 1,
    'limit'    : 10000,
    'datasets' : True,
  }
  if contains:
    params['taskname'] = f'*{contains}*'
  if status:
    params['status'] = status
  r = requests.get(url, params = params, headers = JSON_HEADERS)
  return get_json_request(r)


def get_task(task_id: int) -> dict:
  url = 'https://bigpanda.cern.ch/jobs'
  params = {
    'jeditaskid' : task_id,
    'mode'       : 'nodrop',
  }
  r = requests.get(url, params = params, headers = JSON_HEADERS)
  return get_json_request(r)


def get_job(job_id: int) -> dict:
  url = 'https://bigpanda.cern.ch/job'
  params = {
    'pandaid' : job_id,
  }
  r = requests.get(url, params = params, headers = JSON_HEADERS)
  return get_json_request(r)


def get_files(job_files: dict, dataset: str = '') -> typing.Tuple[str]:
  input_file, output_file, log_file = '', '', ''
  for job_file in job_files:
    lfn = job_file['lfn']

    if job_file['type'] == 'input' and job_file['dataset'] in dataset and not input_file:
      input_file = lfn
    elif job_file['type'] == 'output' and not output_file:
      output_file = lfn
    elif job_file['type'] == 'log' and not log_file:
      log_file = lfn

  return input_file, output_file, log_file


def get_args():
  parser = argparse.ArgumentParser(
    formatter_class = argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument(
    '-c', '--contains', type = str, default = '',
    help = 'Select only those tasks that contain the string',
  )
  parser.add_argument(
    '-s', '--status-include', type = str,
    default = [ status for status in STATUSES if status != 'aborted' ],
    dest = 'status_include', choices = STATUSES, nargs = '+',
    help = 'Select only those tasks that have this status',
  )
  parser.add_argument(
    '-S', '--status-exclude', type = str, default = [ 'aborted' ],
    dest = 'status_exclude', choices = STATUSES, nargs = '+',
    help = 'Exclude those tasks that have this status',
  )
  parser.add_argument(
    '-d', '--days', type = int, default = 14,
    help = 'Exclude those tasks that are not older than that',
  )
  return parser.parse_args()


if __name__ == '__main__':
  args = get_args()

  statuses_include = STATUSES if not args.status_include else args.status_include
  statuses_exclude = args.status_exclude
  statuses_keep = ','.join(set(statuses_include) - set(statuses_exclude))

  name = get_CRIC_name()
  tasks = pbook(name, contains = args.contains, status = statuses_keep, days = args.days)
  for task in tasks:
    task_id = task['jeditaskid']
    if task_id != 41720333:
      continue

    task_datasets = task['datasets']
    dataset_in = ''
    datasets_out = []
    for task_dataset in task_datasets:
      if task_dataset['streamname'] == 'IN':
        dataset_in = task_dataset['datasetname']
      elif task_dataset['streamname'] == 'OUTPUT0':
        datasets_out.append(task_dataset['datasetname'])

    print(f'{task_id}:')
    print(f'  IN:  {dataset_in}')
    print(f"  OUT: {datasets_out[0] if datasets_out else 'n/a'}")
    if len(datasets_out) > 1:
      for dataset_out in datasets_out:
        print(f"       {dataset_out}")

    task_content = get_task(task_id)
    unique_jobs = {}
    for job_info in task_content['jobs']:
      jobid = job_info['pandaid']

      jobid_original_match = JOB_ID_RGX.search(job_info['jobname'])
      jobid_original = int(jobid_original_match.group(1)) if jobid_original_match else jobid

      if jobid_original not in unique_jobs:
        unique_jobs[jobid_original] = []
      unique_jobs[jobid_original].append(jobid)

    print(f'  JOBS:')
    for jobid_original in unique_jobs:
      unique_jobs[jobid_original] = list(sorted(unique_jobs[jobid_original]))
      print(f'    {" -> ".join([ str(jobid) for jobid in unique_jobs[jobid_original] ])}')

      latest_job_id = unique_jobs[jobid_original][-1]

      job_info = get_job(latest_job_id)

      job_files = job_info['files']
      input_file, output_file, log_file = get_files(job_files, dataset_in)
      print(f'        {input_file} -> {output_file} ({log_file})')

      print(f"      => {job_info['job']['jobstatus'].upper()}")
