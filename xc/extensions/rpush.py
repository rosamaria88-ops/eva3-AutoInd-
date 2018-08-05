__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2018 Altertech Group"
__license__ = "https://www.eva-ics.com/license"
__version__ = "1.0.0"
__description__ = "Push client for Roboger"
__api__ = 1
__mods_required__ = ['pyrpush']

__id__ = 'rpush'

__config_help__ = [{
    'name':
    'cf',
    'help':
    'Config file (default: /usr/local/etc/roboger_push.ini',
    'type':
    'str',
    'required':
    False
}]

__functions__ = {
    'push(media_file=None, **kwargs)':
    'Push message (calls pyrpush.Client.push)'
}

__help__ = """
Push client for Roboger event pager (https://www.roboger.com,
https://github.com/alttch/roboger). Refer to pyrpush module documentation for
more info: https://pypi.org/project/pyrpush/
"""

import importlib

from eva.lm.extensions.generic import LMExt as GenericExt
from eva.lm.extapi import log_traceback


class LMExt(GenericExt):

    def __init__(self, cfg=None, info_only=False):
        super().__init__(cfg)
        self.mod_id = __id__
        self.__author = __author__
        self.__license = __license__
        self.__description = __description__
        self.__version = __version__
        self.__mods_required = __mods_required__
        self.__api_version = __api__
        self.__config_help = __config_help__
        self.__functions = __functions__
        self.__help = __help__
        if info_only: return
        try:
            try:
                mod = importlib.import_module('pyrpush')
            except:
                self.log_error('pyrpush Python module not installed')
                raise
            try:
                self.rpush = mod.Client(ini_file=self.cfg.get('cf'))
            except:
                self.log_error('unable to init pyrpush client')
                raise
        except:
            log_traceback()
            self.ready = False

    def push(self, media_file=None, **kwargs):
        try:
            return self.rpush.push(media_file, **kwargs)
        except:
            log_traceback()
            return False