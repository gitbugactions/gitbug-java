import os


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
