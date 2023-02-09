#!/bin/bash

D=$(realpath "$0")
cd "$(dirname "${D}")/.." || exit 1

EVA_DIR=$(pwd)

source <(./sbin/key-as-source config/uc/service UC 2>/dev/null)
source <(./sbin/key-as-source config/lm/service LM 2>/dev/null)
source <(./sbin/key-as-source config/sfa/service SFA 2>/dev/null)

if [ -z "$UC_ENABLED" ] || [ -z "${LM_ENABLED}" ] || [ -z "${SFA_ENABLED}" ]; then
  ./sbin/registry-control restart
  source <(./sbin/key-as-source config/uc/service UC 2>/dev/null)
  source <(./sbin/key-as-source config/lm/service LM 2>/dev/null)
  source <(./sbin/key-as-source config/sfa/service SFA 2>/dev/null)
fi

if [ "$UC_ENABLED" == 1 ]; then
  pgrep -f "${EVA_DIR}/venv/bin/python ${EVA_DIR}/sbin/ucserv.py" > /dev/null || ./sbin/eva-control restart uc
fi

if [ "$LM_ENABLED" == 1 ]; then
  pgrep -f "${EVA_DIR}/venv/bin/python ${EVA_DIR}/sbin/lmserv.py" > /dev/null || ./sbin/eva-control restart lm
fi

if [ "$SFA_ENABLED" == 1 ]; then
  pgrep -f "${EVA_DIR}/venv/bin/python ${EVA_DIR}/sbin/sfaserv.py" > /dev/null || ./sbin/eva-control restart sfa
fi
