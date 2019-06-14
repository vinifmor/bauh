#!/usr/bin/env python3
################################################################
#                                                              #
# EXECUTE THIS SCRIPT INSIDE THE PROJECT FOLDER AS ROOT        #
#                                                              #
################################################################
import os
import sys
from shutil import rmtree

from core import system, flatpak

if not os.geteuid() == 0:
    sys.exit("\nOnly root can run this script\n")


runner_file = '/usr/local/bin/fpakman'
env_name = 'env'


def log(msg: str):
    print('[fpakman] {}'.format(msg))


if os.path.exists(runner_file):
    log('already installed')
    log('Do you wish to uninstall it ? (y/N)')
    uninstall = input()

    if uninstall.lower() == 'y':

        if os.path.exists(runner_file):

            try:
                os.remove(runner_file)
            except:
                log("Could not remove the runner file '{}'".format(runner_file))
                log("Aborting...")
                exit(1)

        if os.path.exists('{}/{}'.format(os.getcwd(), env_name)):
            try:
                rmtree(env_name)
            except:
                log("Could not remove the virtualenv '{}'".format(env_name))
                log("Aborting")
                exit(1)

        log("Successfully uninstalled")

    else:
        log('Aborting...')
else:
    if flatpak.get_version is None:
        print('flatpak seems not to be installed. Aborting...')
        exit(1)

    if not os.path.exists('env'):
        log("Creating a new 'virtualenv' as '{}'...".format(env_name))
        res = system.run_cmd('python3 -m venv ' + env_name)

        if res is None:
            log("Could create a virtualenv for installation. Check if 'virtualenv' is installed.")
            log('Aborting...')
            exit(1)

    res = system.run_cmd('env/bin/pip install -r requirements.txt')

    if res:
        log("Creating runner as '{}'".format(runner_file))
        with open(runner_file, 'w+') as f:
            f.write('#!/bin/bash\n{d}/env/bin/python {d}/app.py'.format(d=os.getcwd()))

        system.run_cmd('chmod +x ' + runner_file)

        log('Successfully installed')
    else:
        log('Could not install python requirements to the virtualenv')
        log('Aborting...')
        exit(1)
