#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from renew_kerit import run_renewal
import sys

if __name__ == "__main__":
    success = run_renewal()
    sys.exit(0 if success else 1)
