#!/usr/bin/env python3

import os

os.system("which python3")
os.system("which pip")
os.system("env | grep VIRT")
os.system("pip install gunicorn")
os.system("./quickinstall.py")
os.system("./m new-wiki")
