__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "3.1.2"

import threading
import cherrypy
import logging
import threading
import time
import os
import sys
import shlex

import eva.core
import eva.runner
import eva.logs

from pyaltt import background_job

from functools import wraps

from eva.api import cp_api_error
from eva.api import cp_bad_request
from eva.api import cp_api_404
from eva.api import api_need_master
from eva.api import parse_api_params

from eva.api import NoAPIMethodException
from eva.api import GenericAPI

from eva.tools import format_json
from eva.tools import fname_remove_unsafe
from eva.tools import val_to_boolean

from eva.exceptions import FunctionFailed
from eva.exceptions import ResourceNotFound

from eva.tools import InvalidParameter
from eva.tools import parse_function_params

from eva.logs import get_log_level_by_name
from eva.logs import get_log_level_by_id

from pyaltt import background_worker

from types import SimpleNamespace

import eva.apikey

import eva.users

import eva.notify

locks = {}
lock_expire_time = {}


def api_need_file_management(f):

    @wraps(f)
    def do(*args, **kwargs):
        if not config.api_file_management_allowed:
            return None
        return f(*args, **kwargs)

    return do


def api_need_cmd(f):

    @wraps(f)
    def do(*args, **kwargs):
        if not eva.apikey.check(kwargs.get('k'), allow=['cmd']):
            return None
        return f(*args, **kwargs)

    return do


def api_need_sysfunc(f):

    @wraps(f)
    def do(*args, **kwargs):
        if not eva.apikey.check(kwargs.get('k'), sysfunc=True):
            return None
        return f(*args, **kwargs)

    return do


def api_need_lock(f):

    @wraps(f)
    def do(*args, **kwargs):
        if not eva.apikey.check(kwargs.get('k'), allow=['lock']):
            return None
        return f(*args, **kwargs)

    return do


class LockAPI(object):

    @api_need_lock
    def lock(self, **kwargs):
        """
        lock token request

        Lock tokens can be used similarly to file locking by the specific
        process. The difference is that SYS API tokens can be:
        
        * centralized for several systems (any EVA server can act as lock
            server)

        * removed from outside

        * automatically unlocked after the expiration time, if the initiator
            failed or forgot to release the lock
        
        used to restrict parallel process starting or access to system
        files/resources. LM PLC :doc:`macro</lm/macros>` share locks with
        extrnal scripts.

        .. note::

            Even if different EVA controllers are working on the same server,
            their lock tokens are stored in different bases. To work with the
            token of each subsystem, use SYS API on the respective
            address/port.

        Args:
            k: .allow=lock
            .l: lock id

        Optional:
            t: maximum time (seconds) to get token
            e: time after which token is automatically unlocked (if absent,
                token may be unlocked only via unlock function)
        """
        l, t, e = parse_api_params(kwargs, 'lte', 'S.n',
                                   {'t': eva.core.timeout})
        if not l in locks:
            locks[l] = threading.Lock()
        logging.debug(
                'acquiring lock %s, timeout = %u, expires = %s' % \
                            (l, t, e))
        if not locks[l].acquire(timeout=t):
            raise FunctionFailed('Unable to acquire lock')
        if e:
            lock_expire_time[l] = time.time() + e
        return True

    @api_need_lock
    def unlock(self, **kwargs):
        """
        release lock token

        Releases the previously obtained lock token.

        Args:
            k: .allow=lock
            .l: lock id

        apidoc_category: lock
        """
        l = parse_api_params(kwargs, 'l', 'S')
        logging.debug('releasing lock %s' % l)
        try:
            locks[l].release()
            return True
        except RuntimeError:
            return True
        except KeyError:
            raise ResourceNotFound()
        except:
            raise FunctionFailed()


cmd_status_created = 0
cmd_status_running = 1
cmd_status_completed = 2
cmd_status_failed = 3
cmd_status_terminated = 4

cmd_status_names = ['created', 'running', 'completed', 'failed', 'terminated']


class CMD(object):

    def __init__(self, cmd, args=None, timeout=None, tki=None):
        self.cmd = fname_remove_unsafe(cmd)
        self.args = args if args else ()
        self.timeout = timeout if timeout else eva.core.timeout
        self.xc = None
        self.status = cmd_status_created
        self.time = {'created': time.time()}

    def run(self):
        self.xc = eva.runner.ExternalProcess(
            eva.core.dir_xc + '/cmd/' + self.cmd,
            args=self.args,
            timeout=self.timeout,
        )
        self.status = cmd_status_running
        self.time['running'] = time.time()
        self.xc.run()

    def update_status(self):
        if self.status == cmd_status_running:
            if self.xc.is_finished():
                if self.xc.exitcode < 0:
                    self.status = cmd_status_terminated
                elif self.xc.exitcode > 0:
                    self.status = cmd_status_failed
                else:
                    self.status = cmd_status_completed
                self.time[cmd_status_names[self.status]] = time.time()

    def serialize(self):
        self.update_status()
        d = {}
        d['cmd'] = self.cmd
        d['args'] = self.args
        d['timeout'] = self.timeout
        d['time'] = self.time
        d['status'] = cmd_status_names[self.status]
        if self.status not in [cmd_status_created, cmd_status_running]:
            d['exitcode'] = self.xc.exitcode
            d['out'] = self.xc.out
            d['err'] = self.xc.err
        return d


class CMDAPI(object):

    @api_need_cmd
    def cmd(self, **kwargs):
        """
        execute a remote system command

        Executes a :ref:`command script<cmd>` on the server where the
        controller is installed.

        Args:
            k: .allow=cmd
            .c: name of the command script

        Optional:
            a: string of command arguments, separated by spaces (passed to the
                script)
            w: wait (in seconds) before API call sends a response. This allows
                to try waiting until command finish
            t: maximum time of command execution. If the command fails to finish
                within the specified time (in sec), it will be terminated
        """
        cmd, args, wait, timeout = parse_api_params(kwargs, 'cawt', 'S.nn')
        if cmd[0] == '/' or cmd.find('..') != -1:
            return None
        if args is not None:
            try:
                _args = tuple(shlex.split(str(args)))
            except:
                _args = tuple(str(args).split(' '))
        else:
            _args = ()
        _c = CMD(cmd, _args, timeout)
        logging.info('executing "%s %s", timeout = %s' % \
                (cmd, ''.join(list(_args)), timeout))
        t = threading.Thread(
            target=_c.run, name='sysapi_c_run_%f' % time.time())
        t.start()
        if wait:
            eva.core.wait_for(_c.xc.is_finished, wait)
        return _c.serialize()


class LogAPI(object):

    @api_need_sysfunc
    def log_rotate(self, **kwargs):
        """
        rotate log file
        
        Equal to kill -HUP <controller_process_pid>.

        Args:
            k: .sysfunc=yes
        """
        parse_api_params(kwargs)
        try:
            eva.core.reset_log()
        except:
            eva.core.log_traceback()
            raise FunctionFailed()
        return True

    @api_need_sysfunc
    def log_debug(self, **kwargs):
        """
        put debug message to log file
        
        An external application can put a message in the logs on behalf of the
        controller.

        Args:
            k: .sysfunc=yes
            m: message text
        """
        m = parse_api_params(kwargs, 'm', '.')
        if m: logging.debug(m)
        return True

    @api_need_sysfunc
    def log_info(self, **kwargs):
        """
        put info message to log file
        
        An external application can put a message in the logs on behalf of the
        controller.

        Args:
            k: .sysfunc=yes
            m: message text
        """
        m = parse_api_params(kwargs, 'm', '.')
        if m: logging.info(m)
        return True

    @api_need_sysfunc
    def log_warning(self, **kwargs):
        """
        put warning message to log file
        
        An external application can put a message in the logs on behalf of the
        controller.

        Args:
            k: .sysfunc=yes
            m: message text
        """
        m = parse_api_params(kwargs, 'm', '.')
        if m: logging.warning(m)
        return True

    @api_need_sysfunc
    def log_error(self, **kwargs):
        """
        put error message to log file
        
        An external application can put a message in the logs on behalf of the
        controller.

        Args:
            k: .sysfunc=yes
            m: message text
        """
        m = parse_api_params(kwargs, 'm', '.')
        if m: logging.error(m)
        return True

    @api_need_sysfunc
    def log_critical(self, **kwargs):
        """
        put critical message to log file
        
        An external application can put a message in the logs on behalf of the
        controller.

        Args:
            k: .sysfunc=yes
            m: message text
        """
        m = parse_api_params(kwargs, 'm', '.')
        if m: logging.critical(m)
        return True

    @api_need_sysfunc
    def log_get(self, **kwargs):
        """
        get records from the controller log

        Log records are stored in the controllers’ memory until restart or the
        time (keep_logmem) specified in controller configuration passes.

        Args:
            k: .sysfunc=yes

        Optional:
            .l: log level (10 - debug, 20 - info, 30 - warning, 40 - error, 50
                - critical)
            t: get log records not older than t seconds
            n: the maximum number of log records you want to obtain
        """
        l, t, n = parse_api_params(kwargs, 'ltn', '.ii')
        if not l: l = 'i'
        return eva.logs.log_get(logLevel=get_log_level_by_name(l), t=t, n=n)

    def log(self, **kwargs):
        """
        put message to log file
        
        An external application can put a message in the logs on behalf of the
        controller.

        Args:
            k: .sysfunc=yes
            l: log level
            m: message text
        """
        k, l, m = parse_function_params(kwargs, 'klm', '.R.', {'l': 'info'})
        log_level = get_log_level_by_id(l)
        f = getattr(self, 'log_' + log_level)
        f(k=k, m=m)
        return True


class FileAPI(object):

    @staticmethod
    def _check_file_name(fname):
        if fname is None or \
                fname[0] == '/' or \
                fname.find('..') != -1:
            raise InvalidParameter('File name contains invalid characters')
        return True

    @staticmethod
    def _file_not_found(fname):
        return ResourceNotFound('File not found {}'.format(fname))

    @api_need_file_management
    @api_need_master
    def file_unlink(self, **kwargs):
        """
        delete file from runtime folder

        Args:
            k: .master
            .i: relative path (without first slash)
        """
        i = parse_api_params(kwargs, 'i', 'S')
        self._check_file_name(i)
        if not os.path.isfile(eva.core.dir_runtime + '/' + i):
            raise self._file_not_found(i)
        try:
            eva.core.prepare_save()
            try:
                os.unlink(eva.core.dir_runtime + '/' + i)
                return True
            finally:
                eva.core.finish_save()
        except:
            eva.core.log_traceback()
            raise FunctionFailed()

    @api_need_file_management
    @api_need_master
    def file_get(self, **kwargs):
        """
        get file contents from runtime folder

        Args:
            k: .master
            .i: relative path (without first slash)
        """
        i = parse_api_params(kwargs, 'i', 'S')
        self._check_file_name(i)
        if not os.path.isfile(eva.core.dir_runtime + '/' + i):
            raise self._file_not_found(i)
        try:
            i = eva.core.dir_runtime + '/' + i
            data = ''.join(open(i).readlines())
            return data, os.access(i, os.X_OK)
        except:
            eva.core.log_traceback()
            raise FunctionFailed()

    @api_need_file_management
    @api_need_master
    def file_put(self, **kwargs):
        """
        put file to runtime folder

        Puts a new file into runtime folder. If the file with such name exists,
        it will be overwritten. As all files in runtime are text, binary data
        can not be put.

        Args:
            k: .master
            .i: relative path (without first slash)
            m: file content
        """
        i, m = parse_api_params(kwargs, 'im', 'Ss')
        self._check_file_name(i)
        try:
            raw = '' if m is None else m
            eva.core.prepare_save()
            try:
                open(eva.core.dir_runtime + '/' + i, 'w').write(raw)
                return True
            finally:
                eva.core.finish_save()
        except:
            eva.core.log_traceback()
            raise FunctionFailed()

    @api_need_file_management
    @api_need_master
    def file_set_exec(self, **kwargs):
        """
        set file exec permission

        Args:
            k: .master
            .i: relative path (without first slash)
            e: *false* for 0x644, *true* for 0x755 (executable)
        """
        i, e = parse_api_params(kwargs, 'ie', 'SB')
        self._check_file_name(i)
        if not os.path.isfile(eva.core.dir_runtime + '/' + i):
            raise self._file_not_found(i)
        try:
            if e: perm = 0o755
            else: perm = 0o644
            eva.core.prepare_save()
            try:
                os.chmod(eva.core.dir_runtime + '/' + i, perm)
            finally:
                eva.core.finish_save()
            return True
        except:
            eva.core.log_traceback()
            return False


class UserAPI(object):

    @api_need_master
    def create_user(self, k, user=None, password=None, key=None):
        return eva.users.create_user(user, password, key)

    @api_need_master
    def set_user_password(self, k, user=None, password=None):
        return eva.users.set_user_password(user, password)

    @api_need_master
    def set_user_key(self, k, user=None, key=None):
        return eva.users.set_user_key(user, key)

    @api_need_master
    def destroy_user(self, k, user=None):
        return eva.users.destroy_user(user)

    @api_need_master
    def list_keys(self, k):
        result = []
        for _k in eva.apikey.keys:
            r = eva.apikey.serialized_acl(_k)
            r['dynamic'] = eva.apikey.keys[_k].dynamic
            result.append(r)
        return sorted(
            sorted(result, key=lambda k: k['key_id']),
            key=lambda k: k['master'],
            reverse=True)

    @api_need_master
    def list_users(self, k):
        return eva.users.list_users()

    @api_need_master
    def get_user(self, k, u):
        return eva.users.get_user(u)

    @api_need_master
    def create_key(self, k, i=None, save=False):
        return eva.apikey.add_api_key(i, save)

    @api_need_master
    def list_key_props(self, k=None, i=None):
        key = eva.apikey.keys_by_id.get(i)
        return None if not key or not key.dynamic else key.serialize()

    @api_need_master
    def set_key_prop(self, k=None, i=None, prop=None, value=None, save=False):
        key = eva.apikey.keys_by_id.get(i)
        return None if not key else key.set_prop(prop, value, save)

    @api_need_master
    def regenerate_key(self, key=None, i=None, save=False):
        return eva.apikey.regenerate_key(i, save)

    @api_need_master
    def destroy_key(self, k=None, i=None):
        return eva.apikey.delete_api_key(i)


class SysAPI(LockAPI, CMDAPI, LogAPI, FileAPI, UserAPI, GenericAPI):

    @api_need_sysfunc
    def save(self, **kwargs):
        """
        save database and runtime configuration

        All modified items, their status, and configuration will be written to
        the disk. If **exec_before_save** command is defined in the
        controller's configuration file, it's called before saving and
        **exec_after_save** after (e.g. to switch the partition to write mode
        and back to read-only).

        Args:
            k: .sysfunc=yes
        """
        parse_api_params(kwargs)
        return eva.core.do_save()

    @api_need_master
    def dump(self, **kwargs):
        parse_api_params(kwargs)
        return eva.core.create_dump()

    @api_need_master
    def get_cvar(self, **kwargs):
        """
        get the value of user-defined variable

        .. note::
        
            Even if different EVA controllers are working on the same
            server, they have different sets of variables To set the variables
            for each subsystem, use SYS API on the respective address/port.

        Args:
            k: .master

        Optional:
            .i: variable name

        Returns:
            Dict containing variable and its value. If no varible name was
            specified, all cvars are returned.
        """
        i = parse_api_params(kwargs, 'i', '.')
        if i:
            return eva.core.get_cvar(i)
        else:
            return eva.core.cvars.copy()

    @api_need_master
    def set_cvar(self, **kwargs):
        """
        set the value of user-defined variable

        Args:
            k: .master
            .i: variable name

        Optional:
            v: variable value (if not specified, variable is deleted)
        """
        i, v = parse_api_params(kwargs, 'iv', 'S.')
        return eva.core.set_cvar(i, v)

    @api_need_master
    def list_notifiers(self, **kwargs):
        """
        list notifiers

        Args:
            k: .master
        """
        parse_api_params(kwargs)
        result = []
        for n in eva.notify.get_notifiers():
            result.append(n.serialize())
        return sorted(result, key=lambda k: k['id'])

    @api_need_master
    def get_notifier(self, **kwargs):
        """
        get notifier configuration

        Args:
            k: .master
            .i: notifier ID
        """
        i = parse_api_params(kwargs, 'i', 'S')
        try:
            return eva.notify.get_notifier(i).serialize()
        except:
            raise ResourceNotFound()

    @api_need_master
    def enable_notifier(self, **kwargs):
        """
        enable notifier

        .. note::

            The notifier is enabled until controller restart. To enable
            notifier permanently, use notifier management CLI.

        Args:
            k: .master
            .i: notifier ID
        """
        i = parse_api_params(kwargs, 'i', 'S')
        try:
            eva.notify.get_notifier(i).enabled = True
        except:
            raise ResourceNotFound()
        return True

    @api_need_master
    def disable_notifier(self, **kwargs):
        """
        disable notifier

        .. note::

            The notifier is disabled until controller restart. To disable
            notifier permanently, use notifier management CLI.

        Args:
            k: .master
            .i: notifier ID
        """
        i = parse_api_params(kwargs, 'i', 'S')
        try:
            eva.notify.get_notifier(i).enabled = False
        except:
            raise ResourceNotFound()
        return True

    @api_need_master
    def set_debug(self, **kwargs):
        """
        switch debugging mode

        Enables and disables debugging mode while the controller is running.
        After the controller is restarted, this parameter is lost and
        controller switches back to the mode specified in the configuration
        file.

        Args:
            k: .master
            debug: true for enabling debug mode, false for disabling
        """
        debug = parse_api_params(kwargs, ('debug',), 'B')
        if debug:
            eva.core.debug_on()
        else:
            eva.core.debug_off()
        return True

    @api_need_master
    def setup_mode(self, **kwargs):
        setup = parse_api_params(kwargs, ('setup',), 'B')
        if not config.api_setup_mode_allowed:
            return False
        if setup:
            eva.core.setup_on()
        else:
            eva.core.setup_off()
        return True

    @api_need_master
    def shutdown_core(self, **kwargs):
        """
        shutdown the controller

        Controller process will be exited and then (should be) restarted by
        watchdog. This allows to restart controller remotely.

        Args:
            k: .master
        """
        parse_api_params(kwargs)
        background_job(eva.core.sighandler_term)()
        return True


class SysHTTP_API_abstract(SysAPI):

    def dump(self, **kwargs):
        fname = super().dump(**kwargs)
        if not fname: raise FunctionFailed()
        return {'file': fname}

    def get_cvar(self, **kwargs):
        result = super().get_cvar(**kwargs)
        return {kwargs['i']: result} if 'i' in kwargs else result

    def file_get(self, **kwargs):
        data, e = super().file_get(**kwargs)
        return { 'file': kwargs.get('i'), 'data': data, 'e': e }

    def create_user(self, k=None, u=None, p=None, a=None):
        """
        create user account

        .. note::
        
            All changes to user accounts are instant, if the system works in
            read/only mode, set it to read/write before performing user
            management.

        Args:
            k: .master
            .u: user login
            p: user password
            a: API key to assign (key id, not a key itself)
        """
        return http_api_result_ok() if super().create_user(k, u, p, a) \
                else http_api_result_error()

    def set_user_password(self, k=None, u=None, p=None):
        """
        set user password

        Args:
            k: .master
            .u: user login
            p: new password
        """
        result = super().set_user_password(k, u, p)
        if result is None: raise cp_api_404()
        return http_api_result_ok() if result else http_api_result_error()

    def set_user_key(self, k=None, u=None, a=None):
        """
        assign API key to user

        Args:
            k: .master
            .u: user login
            a: API key to assign (key id, not a key itself)
        """
        result = super().set_user_key(k, u, a)
        if result is None: raise cp_api_404()
        return http_api_result_ok() if result else http_api_result_error()

    def destroy_user(self, k=None, u=None):
        """
        delete user account

        Args:
            k: .master
            .u: user login
        """
        result = super().destroy_user(k, u)
        if result is None: raise cp_api_404()
        return http_api_result_ok() if result else http_api_result_error()

    def list_keys(self, k=None):
        """
        list API keys

        Args:
            k: .master
        """
        return super().list_keys(k)

    def list_users(self, k=None):
        """
        list user accounts

        Args:
            k: .master
        """
        return super().list_users(k)

    def get_user(self, k=None, u=None):
        """
        get user account info

        Args:
            k: .master
            .u: user login
        """
        result = super().get_user(k=k, u=u)
        if result is None: raise cp_api_404()
        return result

    def create_key(self, k=None, i=None, save=None):
        """
        create API key

        API keys are defined statically in etc/<controller>_apikeys.ini file as
        well as can be created with API and stored in user database.

        Keys with master permission can not be created.

        Args:
            k: .master
            .i: API key ID
            save: save configuration immediately
        """
        result = super().create_key(k, i, save)
        return result if result else http_api_result_error()

    def list_key_props(self, k=None, i=None):
        """
        list API key permissions

        Lists API key permissons (including a key itself)

        .. note::

            API keys, defined in etc/<controller>_apikeys.ini file can not be
            managed with API.

        Args:
            k: .master
            .i: API key ID
            save: save configuration immediately
        """
        result = super().list_key_props(k, i)
        if result is None: raise cp_api_404()
        return result if result else http_api_result_error()

    def set_key_prop(self, k=None, i=None, p=None, v=None, save=None):
        """
        set API key permissions

        Args:
            k: .master
            .i: API key ID
            p: property
            v: value (if none, permission will be revoked)
            save: save configuration immediately
        """
        result = super().set_key_prop(k, i, p, v, save)
        if result is None: raise cp_api_404()
        return http_api_result_ok() if result else http_api_result_error()

    def destroy_key(self, k=None, i=None):
        """
        delete API key

        Args:
            k: .master
            .i: API key ID
        """
        result = super().destroy_key(k, i)
        if result is None: raise cp_api_404()
        return http_api_result_ok() if result else http_api_result_error()

    def regenerate_key(self, k=None, i=None, save=None):
        """
        regenerate API key

        Args:
            k: .master
            .i: API key ID

        Returns:
            JSON dict with new key value in "key" field
        """
        result = super().regenerate_key(k, i, save)
        if result is None: raise cp_api_404()
        return http_api_result_ok({'key':result}) if \
                result else http_api_result_error()


class SysHTTP_API(SysHTTP_API_abstract, eva.api.GenericHTTP_API):

    def __init__(self):
        super().__init__()
        self.expose_api_methods('sysapi')
        self.wrap_exposed()


class SysHTTP_API_REST_abstract:

    def GET(self, rtp, k, ii, full, kind, save, for_dir, props):
        if rtp == 'core':
            return self.test(k=k)
        elif rtp == 'cvar':
            return self.get_cvar(k=k, i=ii)
        elif rtp == 'key':
            if ii:
                return self.list_key_props(k=k, i=ii)
            else:
                return self.list_keys(k=k)
        elif rtp == 'log':
            return self.log_get(
                k=k,
                l=ii,
                t=props.get('t'),
                n=props.get('n'))
        elif rtp == 'notifier':
            if ii:
                return self.get_notifier(k=k, i=ii)
            else:
                return self.list_notifiers(k=k)
        elif rtp == 'runtime':
            return self.file_get(k=k, i=ii)
        elif rtp == 'user':
            if ii:
                return self.get_user(k=k, u=ii)
            else:
                return self.list_users(k=k)
        raise NoAPIMethodException()

    def POST(self, rtp, k, ii, full, kind, save, for_dir, props):
        if rtp == 'core':
            cmd = props.get('cmd')
            if cmd == 'dump':
                return self.dump(k=k)
            elif cmd == 'save':
                return self.save(k=k)
            elif cmd == 'log_rotate':
                return self.log_rotate(k=k)
            elif cmd == 'shutdown':
                return self.shutdown_core(k=k)
            else:
                raise NoAPIMethodException()
        elif rtp == 'log':
            return self.log(k=k, l=ii, m=props.get('m'))
        elif rtp == 'cmd':
            if not ii: raise ResourceNotFound()
            return self.cmd(
                k=k, c=ii, a=props.get('a'), w=props.get('w'), t=props.get('t'))
        raise NoAPIMethodException()

    def PUT(self, rtp, k, ii, full, kind, save, for_dir, props):
        if rtp == 'cvar':
            return self.set_cvar(k=k, i=ii, v=props.get('v'))
        elif rtp == 'key':
            if not SysAPI.create_key(self, k=k, i=ii, save=save):
                raise FunctionFailed()
            for i, v in props.items():
                if not SysAPI.set_key_prop(
                        self, k=k, i=ii, prop=i, value=v, save=save):
                    raise FunctionFailed()
            return True
        elif rtp == 'lock':
            return self.lock(k=k, l=ii, t=props.get('t'), e=props.get('e'))
        elif rtp == 'runtime':
            if not SysAPI.file_put(self, k=k, i=ii, m=props.get('m')):
                raise FunctionFailed()
            if 'e' in props:
                return self.file_set_exec(k=k, i=ii, e=props['e'])
            return True
        elif rtp == 'user':
            return self.create_user(
                k=k, u=ii, p=props.get('p'), a=props.get('a'))
        raise NoAPIMethodException()

    def PATCH(self, rtp, k, ii, full, kind, save, for_dir, props):
        if rtp == 'cvar':
            return self.set_cvar(k=k, i=ii, v=props.get('v'))
        elif rtp == 'core':
            success = False
            if 'debug' in props:
                if not self.set_debug(k=k, debug=props['debug']):
                    raise FunctionFailed()
                success = True
            if 'setup' in props:
                if not self.setup_mode(k=k, setup=props['setup']):
                    raise FunctionFailed()
                success = True
            if success: return True
            else: raise ResourceNotFound()
        elif rtp == 'key':
            for i, v in props.items():
                if not SysAPI.set_key_prop(
                        self, k=k, i=ii, prop=i, value=v, save=save):
                    raise FunctionFailed()
            return True
        elif rtp == 'notifier':
            if not 'enabled' in props:
                raise FunctionFailed()
            return self.enable_notifier(
                k=k, i=ii) if val_to_boolean(
                    props.get('enabled')) else self.disable_notifier(
                        k=k, i=ii)
        elif rtp == 'runtime':
            if not config.api_file_management_allowed:
                if not SysAPI.file_put(self, k=k, i=ii, m=props['m']):
                    raise FunctionFailed()
            if 'e' in props:
                return self.file_set_exec(k=k, i=ii, e=props['e'])
            return True
        elif rtp == 'user':
            if 'p' in props:
                if not SysAPI.set_user_password(
                        self, k=k, user=ii, password=props['p']):
                    raise FunctionFailed()
            if 'a' in props:
                if not SysAPI.set_user_key(self, k=k, user=ii, key=props['a']):
                    raise FunctionFailed()
            return True
        raise NoAPIMethodException()

    def DELETE(self, rtp, k, ii, full, kind, save, for_dir, props):
        if rtp == 'key':
            return self.destroy_key(k=k, i=ii)
        elif rtp == 'lock':
            return self.unlock(k=k, l=ii)
        elif rtp == 'runtime':
            return self.file_unlink(k=k, i=ii)
        elif rtp == 'user':
            return self.destroy_user(k=k, u=ii)
        raise NoAPIMethodException()


def update_config(cfg):
    try:
        config.api_file_management_allowed = (cfg.get(
            'sysapi', 'file_management') == 'yes')
    except:
        pass
    logging.debug('sysapi.file_management = %s' % ('yes' \
            if config.api_file_management_allowed else 'no'))
    try:
        config.api_setup_mode_allowed = (cfg.get('sysapi',
                                                 'setup_mode') == 'yes')
    except:
        pass
    logging.debug('sysapi.setup_mode = %s' % ('yes' \
            if config.api_setup_mode_allowed else 'no'))
    return True


def start():
    http_api = SysHTTP_API()
    cherrypy.tree.mount(http_api, http_api.api_uri)
    lock_processor.start(_interval=eva.core.polldelay)


@eva.core.stop
def stop():
    lock_processor.stop()


@background_worker
def lock_processor(**kwargs):
    for i, v in lock_expire_time.copy().items():
        if time.time() > v:
            logging.debug('lock %s expired, releasing' % i)
            try:
                del lock_expire_time[i]
            except:
                logging.critical('Lock API broken')
            try:
                locks[i].release()
            except:
                pass


api = SysAPI()

config = SimpleNamespace(
    api_file_management_allowed=False, api_setup_mode_allowed=False)
