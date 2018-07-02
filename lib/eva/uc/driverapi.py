__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2018 Altertech Group"
__license__ = "https://www.eva-ics.com/license"
__version__ = "3.1.0"
__api__ = 1

import importlib
import logging
import jsonpickle

import eva.core
from eva.tools import format_json

phis = {}
lpis = {}
drivers = {}
items_by_phi = {}


def get_version():
    return __api__


def get_polldelay():
    return eva.core.polldelay


def get_timeout():
    return eva.core.timeout


def critical():
    return eva.core.critical()


def get_phi(phi_id):
    return phis.get(phi_id)


def get_lpi(lpi_id):
    return lpis.get(lpi_id)


def get_driver(driver_id):
    return drivers.get(driver_id)

def log_traceback():
    return eva.core.log_traceback()

def register_item_update(i):
    u = i.update_exec
    if not u or u[0] != '|' or u.find('.') == -1:
        logging.error(
            'unable to register item ' + \
                    '%s for the driver events, invalid driver str: %s'
            % (i.oid, i.update_exec))
        return False
    phi_id = u[1:].split('.')[0]
    if not phi_id in phis:
        logging.error(
            'unable to register item %s for the driver events, no such PHI: %s'
            % (i.oid, phi_id))
        return False
    items_by_phi[phi_id].add(i)
    logging.debug(
        'item %s registered for driver updates, PHI: %s' % (i.full_id, phi_id))
    return True


def unregister_item_update(i):
    u = i.update_exec
    if not u or u[0] != '|' or u.find('.') == -1:
        logging.error(
            'unable to unregister item ' + \
                    '%s from the driver events, invalid driver str: %s'
            % (i.oid, i.update_exec))
        return False
    phi_id = u[1:].split('.')[0]
    if not phi_id in phis:
        logging.error(
            'unable to unregister item ' + \
                    '%s from the driver events, no such PHI: %s'
            % (i.oid, phi_id))
        return False
    try:
        items_by_phi[phi_id].remove(i)
        logging.debug('item %s unregistered from driver updates, PHI: %s' %
                      (i.full_id, phi_id))
        return True
    except:
        return False


def handle_phi_event(phi, port, data):
    iph = items_by_phi.get(phi.phi_id)
    if iph:
        for i in iph:
            if i.updates_allowed() and not i.is_destroyed():
                logging.debug('event on PHI %s, port %s, updating item %s' %
                              (phi.phi_id, port, i.full_id))
                update_item(i, data)


def update_item(i, data):
    #TODO - handle update event
    pass


def load_phi(phi_id, phi_mod_id, phi_cfg=None, start=True):
    try:
        phi_mod = importlib.import_module('eva.uc.drivers.phi.' + phi_mod_id)
        importlib.reload(phi_mod)
        _api = phi_mod.__api__
        _author = phi_mod.__author__
        _version = phi_mod.__version__
        _description = phi_mod.__description__
        _license = phi_mod.__license__
        logging.info('PHI loaded %s v%s, author: %s, license: %s' %
                     (phi_mod_id, _version, _author, _license))
        logging.debug('%s: %s' % (phi_mod_id, _description))
        if _api > __api__:
            logging.error(
                'Unable to activate PHI %s: ' % phi_mod_id + \
                'controller driver API version is %s, ' % __api__ + \
                'PHI driver API version is %s' % _api)
            return False
    except:
        logging.error('unable to load PHI mod %s' % phi_mod_id)
        eva.core.log_traceback()
        return False
    phi = phi_mod.PHI(phi_cfg=phi_cfg)
    if not phi.ready:
        logging.error('unable to init PHI mod %s' % phi_mod_id)
        return False
    phi.phi_id = phi_id
    if phi_id in phis:
        phis[phi_id].stop()
    phis[phi_id] = phi
    if not phi_id in items_by_phi:
        items_by_phi[phi_id] = set()
    if start: phi.start()
    return phi


def load_lpi(lpi_id, lpi_mod_id, phi_id, lpi_cfg=None, start=True):
    if get_phi(phi_id) is None:
        logging.error('Unable to load LPI, unknown PHI: %s' % phi_id)
        return False
    try:
        lpi_mod = importlib.import_module('eva.uc.drivers.lpi.' + lpi_mod_id)
        importlib.reload(lpi_mod)
        _api = lpi_mod.__api__
        _author = lpi_mod.__author__
        _version = lpi_mod.__version__
        _description = lpi_mod.__description__
        _license = lpi_mod.__license__
        logging.info('LPI loaded %s v%s, author: %s, license: %s' %
                     (lpi_mod_id, _version, _author, _license))
        logging.debug('%s: %s' % (lpi_mod_id, _description))
        if _api > __api__:
            logging.error(
                'Unable to activate LPI %s: ' % lpi_mod_id + \
                'controller driver API version is %s, ' % __api__ + \
                'LPI driver API version is %s' % _api)
            return False
    except:
        logging.error('unable to load LPI mod %s' % lpi_mod_id)
        eva.core.log_traceback()
        return False
    lpi = lpi_mod.LPI(lpi_cfg=lpi_cfg, phi_id=phi_id)
    if not lpi.ready:
        logging.error('unable to init LPI mod %s' % lpi_mod_id)
        return False
    lpi.lpi_id = lpi_id
    lpi.driver_id = phi_id + '.' + lpi_id
    if lpi_id in lpis:
        lpis[lpi_id].stop()
    lpis[lpi_id] = lpi
    drivers[lpi.driver_id] = lpi
    if start: lpi.start()
    return lpi


def unload_phi(phi_id):
    phi = get_phi(phi_id)
    if phi is None: return False
    err = False
    for k, l in lpis.copy().items():
        if l.phi_id == phi_id:
            logging.error(
                'Unable to unload PHI %s, it is in use by LPI %s' % (phi_id, k))
            err = True
    if items_by_phi[phi_id]:
        logging.error(
            'Unable to unload PHI %s, it is in use' %
            (phi_id))
        err = True
    if err: return False
    phi.stop()
    del phis[phi_id]
    return True


def unload_lpi(lpi_id=None, driver_id=None):
    if lpi_id:
        lpi = get_lpi(lpi_id)
    elif driver_id:
        lpi = get_driver(driver_id)
    else:
        return False
    if lpi is None: return False
    err = False
    for i in items_by_phi[lpi.phi_id]:
        if i.update_exec[1:] == driver_id:
            logging.error(
                'Unable to unload driver %s, it is in use' %
                (driver_id))
            err = True
    if err: return False
    lpi.stop()
    del drivers[lpi.driver_id]
    del lpis[lpi.lpi_id]
    return True


def serialize(full=False, config=False):
    return {
        'phi': serialize_phi(full=full, config=config),
        'lpi': serialize_lpi(full=full, config=config)
    }


def serialize_phi(full=False, config=False):
    result = []
    for k, p in phis.copy().items():
        try:
            r = p.serialize(full=full, config=config)
            result.append(r)
        except:
            logging.error('phi %s serialize error' % k)
            eva.core.log_traceback()
    return result


def serialize_lpi(full=False, config=False):
    result = []
    for k, p in lpis.copy().items():
        try:
            r = p.serialize(full=full, config=config)
            result.append(r)
        except:
            logging.error('lpi %s serialize error' % k)
            eva.core.log_traceback()
    return result


def dump():
    return serialize(full=True, config=True)


def load():
    try:
        data = jsonpickle.decode(
            open(eva.core.dir_runtime + '/uc_drivers.json').read())
        _phi = data.get('phi')
        if _phi:
            for p in _phi:
                load_phi(p['id'], p['mod'], phi_cfg=p['cfg'], start=False)
        _lpi = data.get('lpi')
        if _lpi:
            for l in _lpi:
                load_lpi(
                    l['lpi_id'],
                    l['mod'],
                    l['phi_id'],
                    lpi_cfg=l['cfg'],
                    start=False)
    except:
        logging.error('unaboe to load uc_drivers.json')
        eva.core.log_traceback()
        return False
    return True


def save():
    try:
        open(eva.core.dir_runtime + '/uc_drivers.json', 'w').write(
            format_json(serialize(config=True), minimal=False))
    except:
        logging.error('unable to save driver state')
        eva.core.log_traceback()
        return False
    return True


def start():
    eva.core.append_stop_func(stop)
    eva.core.append_dump_func('uc.driverapi', dump)
    eva.core.append_save_func(save)
    for k, p in lpis.items():
        p.start()
    for k, p in phis.items():
        p.start()


def stop():
    for k, p in lpis.items():
        p.stop()
    for k, p in phis.items():
        p.stop()
