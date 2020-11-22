from collections import namedtuple

def merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination

x1 = {'x':'1', 'y':{'xx':'1', 'yy':'5'},}
x2 = {'y':{'xx':'2', 'zz':'34'}, 'z':14}

print(merge(x2,x1))