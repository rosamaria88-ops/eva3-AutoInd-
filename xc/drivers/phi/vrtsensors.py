__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2018 Altertech Group"
__license__ = "https://www.eva-ics.com/license"
__version__ = "1.0.0"
__description__ = "Emulates virtual sensors"

__id__ = 'vrtsensors'
__equipment__ = 'virtual'
__api__ = 1
__required__ = ['port_get', 'value']
__features__ = ['port_get', 'port_set', 'aao_set']
__config_help__ = [{
    'name': 'default_value',
    'help': 'sensors value on load (default: None)',
    'type': 'float',
    'required': False
}]
__get_help__ = []
__set_help__ = []

from eva.uc.drivers.phi.generic_phi import PHI as GenericPHI
from eva.uc.driverapi import handle_phi_event
from eva.uc.driverapi import log_traceback
from eva.uc.driverapi import critical


class PHI(GenericPHI):

    def __init__(self, phi_cfg=None):
        super().__init__(phi_cfg=phi_cfg)
        d = self.phi_cfg.get('default_value')
        if d is None: d = None
        else:
            try:
                d = float(d)
            except:
                d = None
        self.data = {}
        for i in range(1000, 1010):
            self.data[str(i)] = d
        self.phi_mod_id = __id__
        self.__author = __author__
        self.__license = __license__
        self.__description = __description__
        self.__version = __version__
        self.__api_version = __api__
        self.__equipment = __equipment__
        self.__features = __features__
        self.__required = __required__
        self.__config_help = __config_help__
        self.__get_help = __get_help__
        self.__set_help = __set_help__

    def get(self, port=None, cfg=None, timeout=0):
        try:
            return self.data.get(str(port))
        except:
            return None

    def test(self, cmd=None):
        if cmd == 'self':
            return 'OK'
        if cmd == 'get':
            return self.data
        if cmd == 'critical':
            self.log_critical('test')
            return True
        try:
            port, val = cmd.split('=')
            try:
                val = float(val)
                self.data[port] = val
            except:
                self.data[port] = None
            self.log_debug(
                '%s test completed, set port %s=%s' % (self.phi_id, port, val))
            if self.phi_cfg.get('event_on_test_set'):
                handle_phi_event(self, port, self.data)
            return self.data
        except:
            return {
                'get': 'get sensors values',
                'X=S': 'set sensor port X to S'
            }
