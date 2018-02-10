import codecs
import os
import re
import time
from base64 import b64decode

import github3
import networkx as nx
import yaml
from jinja2 import UndefinedError, Template
from jinja2.nodes import Assign


def parsed_meta_yaml(text):
    """
    :param str text: The raw text in conda-forge feedstock meta.yaml file
    :return: `dict|None` -- parsed YAML dict if successful, None if not
    """
    try:
        yaml_dict = yaml.load(Template(text).render())

        # Pull the jinja2 variables out
        t = Template(text)
        variables = {}
        for e in t.env.parse(text).body:
            if isinstance(e, Assign):
                variables[e.target.name] = e.node.value

    except UndefinedError:
        # assume we hit a RECIPE_DIR reference in the vars and can't parse it.
        # just erase for now
        try:
            yaml_dict = yaml.load(
                Template(
                    re.sub('{{ (environ\[")?RECIPE_DIR("])? }}/', '',
                           text)
                ).render())
        except:
            return None
    except:
        return None

    return yaml_dict, yaml.load(text), variables


def source_location(meta_yaml):
    try:
        if 'github.com' in meta_yaml['source']['url']:
            return 'github'
        elif 'pypi.python.org' in meta_yaml['source']['url']:
            return 'pypi'
        else:
            return None
    except KeyError:
        return None


# TODO: with names in a graph
gh = github3.login(os.environ['USERNAME'], os.environ['PASSWORD'])
with open('names.txt', 'r') as f:
    names = f.read().split()


gx = nx.read_gpickle('graph.pkl')

new_names = [name for name in names if name not in gx.nodes]
old_names = [name for name in names if name in gx.nodes]
old_names = sorted(old_names, key=lambda n: gx.nodes[n]['time'])

total_names = new_names + old_names
try:
    for name in total_names:
        feedstock = gh.repository('conda-forge', name + '-feedstock')
        meta_yaml = feedstock.contents('recipe/meta.yaml')
        if meta_yaml:
            text = codecs.decode(b64decode(meta_yaml.content))
            yaml_dict, raw_yaml, jinja_vars = parsed_meta_yaml(text)
            if yaml_dict:
                req = yaml_dict['requirements']
                req = req['build'] + req['run']
                req = set([x.split()[0] for x in req])

                sub_graph = {
                    'name': yaml_dict['package']['name'],
                    'version': yaml_dict['package']['version'],
                    'url': yaml_dict['source']['url'],
                    'raw_url': raw_yaml['source']['url'],
                    'req': req,
                    'time': time.time(),
                    'jinja_vars': jinja_vars
                }

                if name in new_names:
                    gx.add_node(name, **sub_graph)
                else:
                    gx.nodes[name].update(**sub_graph)

except github3.GitHubError:
    pass
for node, attrs in gx.node.items():
    for dep in attrs['req']:
        if dep in gx.nodes:
            gx.add_edge(gx[dep], node)
nx.write_gpickle(gx, 'graph.pkl')
