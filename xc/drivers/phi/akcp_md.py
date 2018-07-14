__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2018 Altertech Group"
__license__ = "https://www.eva-ics.com/license"
__version__ = "1.0.0"
__description__ = "AKCP MD00 motion sensor"

__id__ = 'akcp_md'
__equipment__ = ['AKCP MD00']
__api__ = 1
__required__ = ['port_get', 'value']
__mods_required__ = []
__features__ = ['events']
__config_help__ = [{
    'name': 'host',
    'help': 'AKCP controller ip',
    'type': 'str',
    'required': True
}, {
    'name': 'sp',
    'help': 'controller port where sensor is located (1..X)',
    'type': 'int',
    'required': True
}]
__get_help__ = []
__set_help__ = []

__help__ = """
PHI for AKCP MD00 motion sensor, uses SNMP traps to set sensor status. EVA
sensor should have "port" set to 1 in driver config.

PHI doesn't provide any control/monitoring functions.
"""

from eva.uc.drivers.phi.generic_phi import PHI as GenericPHI
from eva.uc.driverapi import log_traceback
from eva.uc.driverapi import get_timeout
from eva.uc.driverapi import handle_phi_event

from eva.tools import parse_host_port

import eva.uc.drivers.tools.snmp as snmp
import eva.traphandler


class PHI(GenericPHI):

    def __init__(self, phi_cfg=None, info_only=False):
        super().__init__(phi_cfg=phi_cfg, info_only=info_only)
        self.phi_mod_id = __id__
        self.__author = __author__
        self.__license = __license__
        self.__description = __description__
        self.__version = __version__
        self.__api_version = __api__
        self.__equipment = __equipment__
        self.__features = __features__
        self.__required = __required__
        self.__mods_required = __mods_required__
        self.__config_help = __config_help__
        self.__get_help = __get_help__
        self.__set_help = __set_help__
        self.__help = __help__
        if info_only: return
        self.snmp_host, self.snmp_port = parse_host_port(
            self.phi_cfg.get('host'), 161)
        try:
            self.sensor_port = int(self.phi_cfg.get('sp'))
            if self.sensor_port < 1: self.sensor_port = None
        except:
            self.sensor_port = None
        if not self.snmp_host:
            self.log_error('no host specified')
            self.ready = False
        if not self.sensor_port:
            self.log_error('no sensor port specified')
            self.ready = False

    def start(self):
        eva.traphandler.subscribe(self)

    def stop(self):
        eva.traphandler.unsubscribe(self)

    def process_snmp_trap(self, host, data):
        if host != self.snmp_host: return
        if data.get('1.3.6.1.4.1.3854.1.7.4.0') != str(self.sensor_port - 1):
            return
        d = data.get('1.3.6.1.4.1.3854.1.7.1.0')
        if d == '7':
            handle_phi_event(self, self.sensor_port, {'1': False})
        elif d == '2':
            handle_phi_event(self, self.sensor_port, {'1': 0})
        elif d == '4':
            handle_phi_event(self, self.sensor_port, {'1': 1})
        return

    def test(self, cmd=None):
        if cmd == 'self':
            return 'OK'
        return {'-': 'self test only'}
