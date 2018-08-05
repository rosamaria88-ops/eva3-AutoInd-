__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2018 Altertech Group"
__license__ = "https://www.eva-ics.com/license"
__version__ = "1.0.0"
__description__ = "Text-to-speech via ttsbroker"
__api__ = 1
__mods_required__ = ['ttsbroker']

__id__ = 'tts'

__config_help__ = [{
    'name': 'p',
    'help': 'TTS provider',
    'type': 'str',
    'required': True
}, {
    'name': 'k',
    'help': 'provider key file (JSON)',
    'type': 'str',
    'required': False
}, {
    'name':
    'sdir',
    'help':
    'Directory where audio files are permanently stored',
    'type':
    'str',
    'required':
    False
}, {
    'name': 'cdir',
    'help': 'Directory where audio files are cached',
    'type': 'str',
    'required': False
}, {
    'name': 'cf',
    'help': 'Cache format (default: wav)',
    'type': 'str',
    'required': False
}, {
    'name': 'o',
    'help': 'JSON file with default provider options',
    'type': 'str',
    'required': False
}, {
    'name': 'd',
    'help': 'Playback device (list: python3 -m sounddevice',
    'type': 'int',
    'required': False
}, {
    'name': 'g',
    'help': 'Default gain (-10..inf)',
    'type': 'float',
    'required': False
}]

__functions__ = {
    'say(text, **kwargs)': 'Say text (calls ttsbroker.TTSEngine.say)'
}

__help__ = """
Text-to-speech engine via ttsbroker Python module. Refer to module
documentation for more info: https://pypi.org/project/ttsbroker/
"""

import importlib
import json

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
            provider = self.cfg.get('p')
            if not provider:
                self.log_error('no provider specified')
                raise Exception('no provider specified')
            try:
                gain = float(self.cfg.get('gain', 0))
            except:
                self.log_error('invalid gain value: %s' % self.cfg.get('gain'))
                raise
            try:
                if 'd' in self.cfg: device = int(self.cfg.get('d'))
                else: device = None
            except:
                self.log_error('invalid device number: %s' % self.cfg.get('d'))
                raise
            try:
                mod = importlib.import_module('ttsbroker')
            except:
                self.log_error('ttsbroker Python module not installed')
                raise
            try:
                if 'o' in self.cfg:
                    opts = json.load(open(self.cfg.get('o')))
                else:
                    opts = {}
            except:
                self.log_error('invalid options file: %s' % self.cfg.get('o'))
                raise
            try:
                self.tts = mod.TTSEngine(
                    storage_dir=self.cfg.get('sdir'),
                    cache_dir=self.cfg.get('cdir'),
                    cache_format=self.cfg.get('cf', 'wav'),
                    device=device,
                    gain=gain,
                    provider=self.cfg.get('p'),
                    provider_options=opts)
            except:
                self.log_error('unable to init TTS broker')
                raise
            try:
                k = self.cfg.get('k')
                if k:
                    self.tts.set_key(k)
            except:
                self.log_error('unable to set TTS key')
                raise
        except:
            log_traceback()
            self.ready = False

    def say(self, text, **kwargs):
        if text is None: return False
        try:
            return self.tts.say(text, **kwargs)
        except:
            log_traceback()
            return False