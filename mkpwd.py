from passlib.apps import custom_app_context as pwd_context
import getpass
import sys

password = getpass.getpass('Password: ')
print pwd_context.encrypt(password)
