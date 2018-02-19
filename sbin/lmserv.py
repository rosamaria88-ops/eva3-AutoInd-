__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2017 Altertech Group"
__license__ = "See http://www.eva-ics.com/"
__version__ = "3.0.1"

import sys
import os
import getopt

dir_lib = os.path.dirname(os.path.realpath(__file__)) + '/../lib'
sys.path.append(dir_lib)

import eva.core
import eva.notify
import eva.api
import eva.apikey
import eva.lm.controller
import eva.lm.lmapi
import eva.logs

import eva.runner
import eva.sysapi
import eva.wsapi
import eva.mailer


def usage(version_only = False):
    if not version_only: print()
    print('%s version %s build %s ' % \
            (   
                eva.core.product_name,
                eva.core.version,
                eva.core.product_build
            )   
        )   
    if version_only: return
    print ("""Usage: lmserv.py [-f config_file ] [-d]

 -f config_file     start with an alternative config file
 -d                 run in background

for production use lm-control only to start/stop LM PLC
""")


product_build = 2018021902

product_code = 'lm'

eva.core.init()
eva.core.set_product(product_code, product_build)
eva.core.product_name = 'EVA Logic Manager'

_fork = False
_eva_ini = None

try:
    optlist, args = getopt.getopt(sys.argv[1:], 'f:dhV')
except:
    usage()
    sys.exit(4)

for o, a in optlist:
    if o == '-d': _fork = True
    if o == '-f': _eva_ini = a
    if o == '-V':
        usage(version_only = True)
        sys.exit()
    if o == '-h':
        usage()
        sys.exit()

cfg = eva.core.load(fname = _eva_ini, initial = True)
if not cfg: sys.exit(2)

if _fork: eva.core.fork()
eva.core.write_pid_file()

eva.logs.start()

eva.api.update_config(cfg)
eva.sysapi.update_config(cfg)
eva.mailer.update_config(cfg)

eva.core.load_cvars()

eva.apikey.allows = [ 'cmd', 'dm_rules_props', 'dm_rules_list' ]
eva.apikey.load()

eva.notify.init()
eva.notify.load()
eva.notify.start()

eva.lm.controller.init()
eva.lm.controller.load_lvars()
eva.lm.controller.load_remote_ucs()
eva.lm.controller.load_macros()
eva.lm.controller.load_dm_rules()

eva.sysapi.start()
eva.wsapi.start()
eva.lm.lmapi.start()

eva.lm.controller.start()

if eva.core.notify_on_start:
    eva.lm.controller.notify_all(skip_subscribed_mqtt = True)

eva.api.start()

eva.lm.controller.exec_macro('system/autoexec')

eva.core.block()
