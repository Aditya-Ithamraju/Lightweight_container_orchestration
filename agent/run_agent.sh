#!/usr/bin/env bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# set LEADER_ADDR env before running, e.g. export LEADER_ADDR=10.0.0.5:8000
python agent.py
