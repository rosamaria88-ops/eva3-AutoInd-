__author__ = "Altertech Group, https://www.altertech.com/"
__copyright__ = "Copyright (C) 2012-2018 Altertech Group"
__license__ = "https://www.eva-ics.com/license"
__version__ = "3.1.1"

import eva.core
import eva.item
import eva.uc.controller
import threading


class UCItem(eva.item.Item):

    def do_notify(self, skip_subscribed_mqtt=False):
        super().notify(skip_subscribed_mqtt=skip_subscribed_mqtt)
        if eva.core.db_update == 1: eva.uc.controller.save_item_state(self)

    def notify(self, skip_subscribed_mqtt=False):
        t = threading.Thread(
            target=self.do_notify, args=(skip_subscribed_mqtt,))
        t.setDaemon(True)
        t.start()
        eva.uc.controller.handle_event(self)