"""Atajo: python scripts/fetch_ortho.py --region jezero [--center lat,lon] [--hirise-km 5]."""

import sys

from marsmap.terrain.ortho import main

if __name__ == "__main__":
    sys.exit(main())
