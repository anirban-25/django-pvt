import os


def doesFileExist(path, name):
    if path[:-1] == "/":
        return os.path.exists(path + name)
    else:
        return os.path.exists(path + "/" + name)
