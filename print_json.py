#!/usr/bin/env python

import sys
import json

input_data = sys.stdin.read()
try:
  parsed_data = json.loads(input_data)
  print(json.dumps(parsed_data, indent = 2))
except ValueError as e:
  print('Invalid JSON input:', e)

