#!/usr/bin/env python

import os
import json
import requests
import argparse
import re
import typing
import datetime
import time
import tabulate
import copy

from rucio.client import Client


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

PANDA_NO_ERROR = ''
PANDA_ERRORS = {
  'ddm:200'           : 'Expected output *.log.tgz is missing in pilot JSON',
  'jobdispatcher:100' : 'Lost heartbeat',
  'pilot:1137'        : 'Failed to stage-out file: *.tgz from the site, no protocol for provided setting found',
  'pilot:1151'        : 'File transfer timed out during stage-in: *.tgz from the site, copy command timed out',
  'pilot:1152'        : 'File transfer timed out during stage-out: *.tgz to a site, copy command timed out',
  'sup:9000'          : 'Worker canceled by harvester due to held too long or not found',
  'taskbuffer:300'    : 'The worker was cancelled while the job was starting',
  'pilot:1326'        : 'No matching replicas were found (failed to transfer files using rucio)',
  PANDA_NO_ERROR      : '(no errors)',
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


def print_stats(site_stats: dict, site_attempts: dict, error_messages: dict, indentation: int = 0) -> None:
  site_stats_sorted = list(sorted(site_stats.items(), key = lambda kv: sum(kw[1] for kw in kv[1].items()), reverse = True))
  table_data = [ [ 'Site', 'Errors', 'Description', 'Attempts', 'Success rate [%]' ] ]
  for site_name, site_errors in site_stats_sorted:
    attempts = site_attempts[site_name]
    if not attempts:
      continue

    successes = 0 if PANDA_NO_ERROR not in site_errors else site_errors[PANDA_NO_ERROR]
    site_errors_sorted = list(sorted(site_errors.items(), key = lambda kv: kv[1], reverse = True))

    rows = []
    for err_idx, err_data in enumerate(site_errors_sorted):
      error_message = ''
      err, err_count = err_data
      if err in PANDA_ERRORS:
        error_message = PANDA_ERRORS[err]
      elif err in error_messages:
        error_message = error_messages[err]
      else:
        raise RuntimeError(f'Could not find error message for the following code: {err}')

      rows.append([
        '' if err_idx else site_name,
        f'{err} ({err_count})' if err != PANDA_NO_ERROR else f'({err_count})',
        error_message,
        '' if err_idx else attempts,
        '' if err_idx else f'{successes / attempts * 100:.0f}%',
      ])
    table_data.extend(rows)
  table = tabulate.tabulate(table_data, headers = 'firstrow', tablefmt = 'rounded_outline')
  indented_table = '\n'.join(' ' * indentation + line for line in table.splitlines())
  print(indented_table)


def merge_stats(first: dict, second: dict) -> dict:
  new = copy.deepcopy(first)
  for site_name, site_data in second.items():
    if site_name not in new:
      new[site_name] = site_data
    else:
      for site_error, error_count in site_data.items():
        if site_error not in new[site_name]:
          new[site_name][site_error] = error_count
        else:
          new[site_name][site_error] += error_count
  return new


def merge_attempts(first: dict, second: dict) -> dict:
  new = copy.deepcopy(first)
  for site_name, nof_attempts in second.items():
    if site_name in new:
      new[site_name] += nof_attempts
    else:
      new[site_name] = nof_attempts
  return new


def get_job_id_str(job_info: dict) -> str:
  job_id_str = str(job_info['id'])
  return f'({job_id_str})' if job_info['is_retasked'] else job_id_str


def extract_scope_and_name(dataset: str) -> dict:
  if dataset.endswith('/'):
    dataset = dataset[:-1]
  if ':' in dataset:
    dataset_split = dataset.split(':')
    return { 'scope' : dataset_split[0], 'name' : dataset_split[1] }
  if dataset.startswith('user.'):
    return { 'scope' : dataset[:dataset.find('.', dataset.find('.') + 1)], 'name' : dataset }
  raise RuntimeError(f'Unable to extract scope and name from: {dataset}')


def list_replica_sites(client: Client, scope: str, name: str) -> dict:
  gen = client.list_replicas([ { 'scope' : scope, 'name' : name } ])
  replica = None
  for tmp in gen:
    assert(not replica)
    replica = tmp
  return list(sorted([ k for k, v in replica['states'].items() if v == 'AVAILABLE' ]))


def print_dataset_info(client: Client, dataset: str, indent: int = 0) -> dict:
  scope_name = extract_scope_and_name(dataset)
  gen = client.list_files(**scope_name)
  space = ' ' * indent
  dataset_info = { dataset : {} }
  for f in gen:
    sites = list_replica_sites(client, f['scope'], f['name'])
    dataset_info[dataset][f['name']] = { 'nevents' : f['events'], 'sites' : sites }

    dataset_str = f'{space}{f["name"]}: '
    if f['events'] is not None:
      dataset_str += f'{f["events"]} events, '
    num_sites = len(sites)
    dataset_str += f'{num_sites} {pluralize("site", num_sites)} ({", ".join(sites)})'
    print(dataset_str)

  return dataset_info


def print_summary(tasks_summary: dict):
  table_data = [ [ 'Task ID', 'Datasets', 'Attempts', 'Files', 'Events', 'Completed [%]', 'Status' ] ]
  datasets_to_copy = []
  tasks_sorted = list(sorted(tasks_summary.items(), key = lambda kv: kv[1]['percentage'], reverse = True))
  for task_id, task_data in tasks_sorted:
    rows = [[
      task_id,
      'IN:  ' + boldify(extract_scope_and_name(task_data['datasets_in'][0])['name']),
      task_data['total_attempts'],
      f'{task_data["nfiles_done"]}/{task_data["nfiles_out"]}',
      f'{boldify(task_data["nevents_processed"])}/{task_data["nevents"]}',
      boldify(f'{task_data["percentage"]:3.1f}'),
      colorize(task_data['status']),
    ]]

    for dataset_in in task_data['datasets_in'][1:]:
      rows.append([ '', f'     {boldify(extract_scope_and_name(dataset_in)["name"])}', '', '', '', '', '' ])
    for dataset_idx, dataset_out in enumerate(task_data['datasets_out']):
      rows.append([ '', f'{"    " if dataset_idx else "OUT:"} {extract_scope_and_name(dataset_out)["name"]}', '', '', '', '', '' ])

    datasets_to_copy.extend(task_data['datasets_out'])
    table_data.extend(rows)

  table = tabulate.tabulate(table_data, headers = 'firstrow', tablefmt = 'rounded_outline', stralign = 'left')
  print(table)

  if datasets_to_copy:
    print(f'\nTo download all {len(datasets_to_copy)} datasets with rucio, use the following command:\n')
    print('  rucio download \\')
    for dataset_idx, dataset_name in enumerate(datasets_to_copy):
      str_to_print = dataset_name
      if dataset_idx < len(datasets_to_copy) - 1:
        str_to_print += ' \\'
      print(f'    {str_to_print}')


if __name__ == '__main__':
  args = get_args()

  statuses_include = STATUSES if not args.status_include else args.status_include
  statuses_exclude = args.status_exclude
  statuses_keep = ','.join(set(statuses_include) - set(statuses_exclude))

  rucio_client = Client()

  name = args.user if args.user else get_CRIC_name()
  tasks = pbook(name, contains = args.contains, status = statuses_keep, days = args.days)
  num_tasks = len(tasks)
  print(boldify(f'Found {num_tasks} {pluralize("task", num_tasks)}'))

  error_messages = {}
  all_site_stats = {}
  all_site_attempts = {}

  tasks_summary = {}

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
      elif task_dataset['streamname'] == 'OUTPUT0' and task_dataset['nfiles'] > 0:
        datasets_out.append(task_dataset['datasetname'])

    dataset_in_info = {}
    dataset_out_info = {}
    print(f'{boldify("TASK")} {task_id}:')
    print(f'  {boldify("IN")}:     {datasets_in[0] if datasets_in else "n/a"}')
    if datasets_in:
      dataset_in_info.update(print_dataset_info(rucio_client, datasets_in[0], 12))
    if len(datasets_in) > 1:
      for dataset_in in datasets_in[1:]:
        print(f'          {dataset_in}')
        dataset_in_info.update(print_dataset_info(rucio_client, dataset_in, 12))
    print(f'  {boldify("OUT")}:    {datasets_out[0] if datasets_out else "n/a"}')
    if datasets_out:
      dataset_out_info.update(print_dataset_info(rucio_client, datasets_out[0], 12))
    if len(datasets_out) > 1:
      for dataset_out in datasets_out[1:]:
        print(f'          {dataset_out}')
        dataset_out_info.update(print_dataset_info(rucio_client, dataset_out, 12))

    task_status = task['status']
    tasks_summary[task_id] = {
      'datasets_in'    : datasets_in,
      'datasets_out'   : datasets_out,
      'total_attempts' : 0,
      'status'         : task_status,
    }

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

      tasks_summary[task_id].update({
        'nfiles_out' : nfiles,
        'nfiles_done' : nfiles_finished,
        'nevents' : nevents_str,
        'nevents_processed' : nevents_processed_str,
        'percentage' : pct,
      })

      progress = f' ({nfiles_finished}/{nfiles} {pluralize("file", nfiles)}, {nevents_processed_str}/{nevents_str} events, {pct:.0f}%)'
    print(f'  {boldify("STATUS")}: {colorize(task_status)}{progress}')

    task_content = get_task(task_id)
    task_jobs = task_content['jobs']
    task_errs = task_content['errsByCount']

    unique_jobs = {}
    task_site_stats = {}
    task_site_attempts = {}

    for job_info in task_jobs:
      if job_info['prodsourcelabel'] != 'user':
        # Consider only user runGen jobs
        continue

      jobid = job_info['pandaid']

      jobid_original_match = JOB_ID_RGX.search(job_info['jobname'])
      jobid_original = int(jobid_original_match.group(1)) if jobid_original_match else jobid

      jobid_str = str(jobid)
      job_errs = []
      for task_err in task_errs:
        if jobid_str in task_err['pandalist']:
          error_code = task_err['error']
          if error_code not in PANDA_ERRORS and error_code not in error_messages:
            error_messages[error_code] = task_err['diag']
          job_errs.append(error_code)

      if jobid_original not in unique_jobs:
        unique_jobs[jobid_original] = []
      job_site = job_info['computingsite']
      is_retasked = job_info['taskbuffererrorcode'] != 0 # reassigned by jedi or killed by panda
      unique_jobs[jobid_original].append({ 'id': jobid, 'site' : job_site, 'errs' : job_errs, 'is_retasked' : is_retasked })


    print(f'  {boldify("JOBS")} ({len(unique_jobs)}):')
    earliest_time = time.time()
    latest_time = 0
    for jobid_original in unique_jobs:
      unique_jobs_id = list(sorted(unique_jobs[jobid_original], key = lambda kv: kv['id']))

      first_job_id = unique_jobs_id[0]['id']
      latest_job_id = unique_jobs_id[-1]['id']

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

      job_ids_per_line = 8
      job_chain_str = ''
      job_chain_str_indent = ''
      num_unique_jobs_id = len(unique_jobs_id)
      for line_num in range(0, num_unique_jobs_id, job_ids_per_line):
        if line_num > 0:
          job_chain_str += ' ->\n'
        job_chain_chunk = unique_jobs_id[line_num:line_num + job_ids_per_line]
        if not job_chain_str_indent:
          job_chain_str_indent = ' ' * (len(str(job_chain_chunk[0]['id'])) + 4) + ' -> '
        else:
          job_chain_str += job_chain_str_indent
        job_chain_str += ' -> '.join([ get_job_id_str(job_chunk) for job_chunk in job_chain_chunk ])
      print(f'    {job_chain_str}')
      print(f'        # resubmissions: {num_unique_jobs_id - 1}')
      print(f'        time elapsed:    {job_chain_elapsed}')
      print(f'        log file:        {log_file}')
      print(f'        inputs:          {input_files[0]}')
      for input_file in input_files[1:]:
        print(f'                         {input_file}')
      print(f'        output:          {output_file}')
      print(f'        status:          {colorize(job_info["job"]["jobstatus"].upper())}')

      site_stats = {}
      site_attempts = {}
      for job_stats in unique_jobs_id:
        site = job_stats['site']
        errs = job_stats['errs']
        if site not in site_stats:
          site_stats[site] = {}
        if site not in site_attempts:
          site_attempts[site] = 0

        if not job_stats['is_retasked']:
          for err in errs:
            if err not in site_stats[site]:
              site_stats[site][err] = 0
            site_stats[site][err] += 1
          if not errs :
            if PANDA_NO_ERROR not in site_stats[site]:
              site_stats[site][PANDA_NO_ERROR] = 0
            site_stats[site][PANDA_NO_ERROR] += 1

          site_attempts[site] += 1
      print_stats(site_stats, site_attempts, error_messages, 4)

      task_site_stats = merge_stats(task_site_stats, site_stats)
      task_site_attempts = merge_attempts(task_site_attempts, site_attempts)

      tasks_summary[task_id]['total_attempts'] += sum(site_attempts.values())

    print(f'  {boldify("TOTAL TIME ELAPSED")}: {seconds_to_human_readable(latest_time - earliest_time)}')
    print_stats(task_site_stats, task_site_attempts, error_messages, 2)


    all_site_stats = merge_stats(all_site_stats, task_site_stats)
    all_site_attempts = merge_attempts(all_site_attempts, task_site_attempts)

    if task_idx < (num_tasks - 1):
      print('\n\n')

  print_stats(all_site_stats, all_site_attempts, error_messages)
  print_summary(tasks_summary)
