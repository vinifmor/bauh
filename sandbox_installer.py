#!/usr/bin/env python3
################################################################
# It installs the application without compromising you system. #
# libraries. 'qt5' is required to be installed.                #
#                                                              #
# If you use GTK, install 'libappindicator3' also.             #
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


link_path = '/usr/local/bin/fpakman'
runner_file = 'run.sh'
env_name = 'env'


def log(msg: str):
    print('[fpakman] {}'.format(msg))


if os.path.exists(link_path):
    log('already installed')
    log('Do you wish to uninstall it ? (y/N)')
    uninstall = input()

    if uninstall.lower() == 'y':

        try:
            os.unlink(link_path)
        except:
            log("Could not remove the runner syslink '{}'".format(link_path))
            log("Aborting...")
            exit(1)

        if os.path.exists('{}/{}'.format(os.getcwd(), env_name)):
            try:
                rmtree(env_name)
            except:
                log("Could not remove the virtualenv '{}'".format(env_name))
                log("Aborting")
                exit(1)

        if os.path.exists('{}/{}'.format(os.getcwd(), runner_file)):

            try:
                os.remove(runner_file)
            except:
                log("Could not remove the runner file '{}'".format(runner_file))
                log("Aborting...")
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
        with open('run.sh', 'w+') as f:
            f.write('#!/bin/bash\n{d}/env/bin/python {d}/app.py'.format(d=os.getcwd()))

        system.run_cmd('chmod +x ' + runner_file)

        log("Creating syslink as '{}'".format(link_path))

        try:
            os.link('{}/{}'.format(os.getcwd(), runner_file), link_path)
        except:
            log("Could not create the syslink")
            log("Aborting...")
            exit(1)

        log('Successfully installed')
    else:
        log('Could not install python requirements to the virtualenv')
        log('Aborting...')
        exit(1)
