import sys
from arras.devhost import main
from arras.distribution import DistributionConfig

main(['--port', sys.argv[2]], distribution=DistributionConfig(theme_manifest=sys.argv[1]))
