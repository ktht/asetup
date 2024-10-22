#!/usr/bin/env python

import os
import json
import requests
import argparse
import re
import typing
import datetime
import time


JSON_HEADERS = {
  'Accept'       : 'application/json',
  'Content-Type' : 'application/json',
}

# statuses not listed in the following: assigning, exhausted, paused, ready, registered, running, submitting, scouting, staged
STATUSES = [ 'aborted', 'broken', 'done', 'failed', 'finished', 'pending', 'running' ]

JOB_ID_RGX = re.compile(r'/\.(\d+)$')

ANSI_RESET = '\033[0m'
ANSI_COLORS = {
  'red'   : '\033[31m',
  'green' : '\033[32m',
  'blue'  : '\033[34m',
  'grey'  : '\033[90m'
}
ANSI_BOLD = '\033[1m'

PANDA_ERRORS = {
  'ddm:200'           : 'Expected output *.log.tgz is missing in pilot JSON',
  'jobdispatcher:100' : 'Lost heartbeat',
  'pilot:1137'        : 'Failed to stage-out file: *.tgz from the site, no protocol for provided setting found',
  'pilot:1151'        : 'File transfer timed out during stage-in: *.tgz from the site, copy command timed out',
  'pilot:1152'        : 'File transfer timed out during stage-out: *.tgz to a site, copy command timed out',
  'sup:9000'          : 'Worker canceled by harvester due to held too long or not found',
  'taskbuffer:300'    : 'The worker was cancelled while the job was starting',
}


def colorize(text: str, lower: bool = True) -> str:
  color = ''
  if text in [ 'broken', 'failed', 'FAILED', 'finished' ]:
    color  = 'red'
  elif text in [ 'done', 'FINISHED' ]:
    color = 'green'
  elif text.lower() in [ 'starting', 'running' ]:
    color = 'blue'
  elif text == 'pending':
    color = 'grey'
  text_tf = text.lower() if lower else text
  return ANSI_COLORS[color] + text_tf + ANSI_RESET if color else text_tf


def boldify(text: str) -> str:
  return ANSI_BOLD + text + ANSI_RESET


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


def values_to_matching_keys(list_of_dicts: typing.List[dict], condition: typing.Callable[[dict], bool]) -> typing.List[str]:
  return [ dict_entry['lfn'] for dict_entry in list_of_dicts if condition(dict_entry) ]


def get_output_lfn(job_files: typing.List[dict], field_name: str) -> str:
  matching_files = values_to_matching_keys(job_files, lambda dict_entry: dict_entry['type'] == field_name)
  if matching_files:
    return matching_files[0]
  return 'n/a'


def get_input_lfns(job_files: typing.List[dict], input_datasets: str) -> typing.List[str]:
  return values_to_matching_keys(
    job_files,
    lambda dict_entry: dict_entry['type'] == 'input' and
                       any(dict_entry['scope'] in input_dataset for input_dataset in input_datasets)
  )


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
  parser.add_argument(
    '-u', '--user', type = str, default = '', dest = 'user',
    help = 'User whose tasks are shown',
  )
  parser.add_argument(
    '-t', '--task-id', type = int, default = [], nargs = '+', dest = 'task_id',
    help = 'Task IDs to filter',
  )
  return parser.parse_args()


def int_to_si(n: int) -> str:
  sfxs = [ '', 'k', 'M', 'B' ]
  idx = 0

  while abs(n) >= 1000. and idx < len(sfxs) - 1:
    idx += 1
    n /= 1000.

  return f'{n:.0f}{sfxs[idx]}'


def date_to_unix(date: str) -> int:
  return int(datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S').timestamp())


def find_job_from_task(list_of_jobs: dict, job_id: int):
  for job_info in list_of_jobs:
    if job_info['pandaid'] == job_id:
      return job_info
  return {}


def get_start_time(list_of_jobs: dict, job_id: int) -> int:
  job_info = find_job_from_task(list_of_jobs, job_id)
  assert(job_info)
  return date_to_unix(job_info['creationtime'])


def get_end_time(list_of_jobs: dict, job_id: int) -> int:
  job_info = find_job_from_task(list_of_jobs, job_id)
  assert(job_info)
  return date_to_unix(job_info['endtime']) if job_info['endtime'] else int(time.time())


def pluralize(word: str, count: int):
  return f'{word}s' if count != 1 else word


def seconds_to_human_readable(seconds: int) -> str:
  days = seconds // (24 * 3600)
  seconds %= (24 * 3600)
  hours = seconds // 3600
  seconds %= 3600
  minutes = seconds // 60
  seconds %= 60
  parts = []
  if days > 0:
    parts.append(f'{days} {pluralize("day", days)}')
  if hours > 0 or parts:
    parts.append(f'{hours} {pluralize("hour", hours)}')
  if minutes > 0 or parts:
    parts.append(f'{minutes} {pluralize("minute", minutes)}')
  if seconds > 0 or parts:
    parts.append(f'{int(seconds)} {pluralize("second", seconds)}')
  return ', '.join(parts)


if __name__ == '__main__':
  args = get_args()

  statuses_include = STATUSES if not args.status_include else args.status_include
  statuses_exclude = args.status_exclude
  statuses_keep = ','.join(set(statuses_include) - set(statuses_exclude))
  #TODO errors and computing sites (per task, across all tasks)
  # need to utilize as much information that's available in the task json as possible bc querying every job expensive
  # query jobs explicitly if they are not listed in task error summary
  #TODO summary: input & output datasets, their completion rate, errors & sites
  # dataset, completion rate

  name = args.user if args.user else get_CRIC_name()
  tasks = pbook(name, contains = args.contains, status = statuses_keep, days = args.days)
  num_tasks = len(tasks)
  print(boldify(f'Found {num_tasks} {pluralize("task", num_tasks)}'))

  error_messages = {}

  for task_idx, task in enumerate(tasks):
    task_id = task['jeditaskid']
    if args.task_id and task_id not in args.task_id:
      continue

    task_datasets = task['datasets']
    datasets_in = []
    datasets_out = []
    for task_dataset in task_datasets:
      if task_dataset['streamname'].startswith('IN'):
        datasets_in.append(task_dataset['datasetname'])
      elif task_dataset['streamname'] == 'OUTPUT0':
        datasets_out.append(task_dataset['datasetname'])

    print(f'{boldify("TASK")} {task_id}:')
    print(f'  {boldify("IN")}:     {datasets_in[0] if datasets_in else "n/a"}')
    if len(datasets_in) > 1:
      for dataset_in in datasets_in:
        print(f'          {dataset_in}')
    print(f'  {boldify("OUT")}:    {datasets_out[0] if datasets_out else "n/a"}')
    if len(datasets_out) > 1:
      for dataset_out in datasets_out:
        print(f'          {dataset_out}')

    task_status = task['status']
    progress = ''
    if datasets_in:
      dsinfo = task['dsinfo']
      nfiles = dsinfo['nfiles']
      nfiles_finished = dsinfo['nfilesfinished']
      nevents = dsinfo['neventsTot']
      nevents_processed = dsinfo['neventsUsedTot']
      pct = nevents_processed / nevents * 100
      nevents_str = int_to_si(nevents)
      nevents_processed_str = int_to_si(nevents_processed)
      progress = f' ({nfiles_finished}/{nfiles} {pluralize("file", nfiles)}, {nevents_processed_str}/{nevents_str} events, {pct:.0f}%)'
    print(f'  {boldify("STATUS")}: {colorize(task_status)}{progress}')

    task_content = get_task(task_id)
    task_jobs = task_content['jobs']
    unique_jobs = {}
    for job_info in task_jobs:
      if job_info['prodsourcelabel'] != 'user':
        # Consider only user runGen jobs
        continue

      jobid = job_info['pandaid']

      jobid_original_match = JOB_ID_RGX.search(job_info['jobname'])
      jobid_original = int(jobid_original_match.group(1)) if jobid_original_match else jobid

      if jobid_original not in unique_jobs:
        unique_jobs[jobid_original] = []
      unique_jobs[jobid_original].append({ 'id': jobid })

    print(f'  {boldify("JOBS")} ({len(unique_jobs)} {pluralize("chain", len(unique_jobs))}):')
    earliest_time = time.time()
    latest_time = 0
    for jobid_original in unique_jobs:
      unique_jobs[jobid_original] = list(sorted(unique_jobs[jobid_original], key = lambda kv: kv['id']))

      first_job_id = unique_jobs[jobid_original][0]['id']
      latest_job_id = unique_jobs[jobid_original][-1]['id']

      job_info = get_job(latest_job_id)

      job_files = job_info['files']
      input_files = get_input_lfns(job_files, datasets_in)
      output_file = get_output_lfn(job_files, 'output')
      log_file = get_output_lfn(job_files, 'log')
      if not input_files:
        continue

      job_chain_start = get_start_time(task_jobs, first_job_id)
      job_chain_end = get_end_time(task_jobs, latest_job_id)
      job_chain_elapsed = seconds_to_human_readable(job_chain_end - job_chain_start)

      earliest_time = min(earliest_time, job_chain_start)
      latest_time = max(latest_time, job_chain_end)

      print(f'    {" -> ".join([ str(jobid["id"]) for jobid in unique_jobs[jobid_original] ])} ({job_chain_elapsed})')
      print(f'        {input_files[0]} -> {output_file} ({log_file})')
      for input_file in input_files[1:]:
        print(f'        {input_file}')
      print(f'      => {colorize(job_info["job"]["jobstatus"].upper())}')
    print(f'  {boldify("TIME ELAPSED")}: {seconds_to_human_readable(latest_time - earliest_time)}')

    print(json.dumps(task_content['errsByCount'], indent = 2))
    if task_idx < (num_tasks - 1):
      print('\n')
