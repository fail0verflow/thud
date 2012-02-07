#!/usr/bin/env python2.7
from passlib.apps import custom_app_context as pwd_context
import getpass

password = getpass.getpass('Password: ')
print pwd_context.encrypt(password)
