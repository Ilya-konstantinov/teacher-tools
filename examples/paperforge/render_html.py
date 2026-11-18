#!/usr/bin/env python3
"""Example external renderer: contract JSON on stdin, HTML on stdout."""
import html
import json
import sys

payload = json.load(sys.stdin)
if payload['schema_version'] != 1:
    raise ValueError('Unsupported document contract')
print('<!doctype html><html><head><meta charset="utf-8"><title>Paperforge</title></head><body>')
for ticket in payload['tickets']:
    print(f'<h1>Paper {ticket["ticket"]}</h1><ol>')
    for question in ticket['questions']:
        print('<li>' + html.escape(question['text']))
        for label, text in question.get('options', []):
            print('<p>' + html.escape(label + '. ' + text) + '</p>')
        if payload['mode'] == 'answers':
            print('<p><strong>Answer:</strong> ' + html.escape(question['answer_text']) + '</p>')
        print('</li>')
    print('</ol>')
print('</body></html>')
