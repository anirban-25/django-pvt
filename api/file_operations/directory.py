import os


def create_dir(DIR_PATH):
    if not os.path.exists(DIR_PATH):
        os.makedirs(DIR_PATH)
